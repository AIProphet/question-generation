import os,time, json, datetime

# model_type = "SEQ2SEQ"
model_type = "MALUUBA"

# CUDA config
os.environ["CUDA_VISIBLE_DEVICES"]="2"
mem_limit=0.5

import tensorflow as tf
import numpy as np
import helpers.loader as loader
import helpers.metrics as metrics
import helpers.preprocessing as preprocessing
import helpers.ops as ops
from helpers.output import output_pretty, tokens_to_string, output_eval
from tqdm import tqdm

from seq2seq_model import Seq2SeqModel
from maluuba_model import MaluubaModel
from datasources.squad_streamer import SquadStreamer
from langmodel.lm import LstmLmInstance
from qa.mpcm import MpcmQaInstance

import flags

FLAGS = tf.app.flags.FLAGS

def main(_):
    chkpt_path = FLAGS.model_dir+'saved/qgen-maluuba-filt'
    # chkpt_path = FLAGS.model_dir+'qgen/SEQ2SEQ/'+'1528886861'

    # load dataset
    train_data = loader.load_squad_triples(FLAGS.data_path, False)
    dev_data = loader.load_squad_triples(FLAGS.data_path, True)[:1500]

    if FLAGS.filter_window_size >-1:
        train_data = preprocessing.filter_squad(train_data, window_size=FLAGS.filter_window_size, max_tokens=FLAGS.filter_max_tokens)
        dev_data = preprocessing.filter_squad(dev_data, window_size=FLAGS.filter_window_size, max_tokens=FLAGS.filter_max_tokens)


    print('Loaded SQuAD with ',len(train_data),' triples')
    print('Loaded SQuAD dev set with ',len(dev_data),' triples')
    train_contexts, train_qs, train_as,train_a_pos = zip(*train_data)
    dev_contexts, dev_qs, dev_as, dev_a_pos = zip(*dev_data)


    # vocab = loader.get_vocab(train_contexts, tf.app.flags.FLAGS.vocab_size)
    with open(chkpt_path+'/vocab.json') as f:
        vocab = json.load(f)

    dev_data_source = SquadStreamer(vocab, FLAGS.eval_batch_size, 1, shuffle=False)


    # Create model
    if model_type == "SEQ2SEQ":
        model = Seq2SeqModel(vocab, training_mode=True)
    elif model_type == "MALUUBA":
        # TEMP - no need to spin up the LM or QA model at eval time
        FLAGS.qa_weight = 0
        FLAGS.lm_weight = 0
        model = MaluubaModel(vocab, training_mode=True, lm_weight=FLAGS.lm_weight, qa_weight=FLAGS.qa_weight)
    else:
        exit("Unrecognised model type: "+model_type)

    with model.graph.as_default():
        saver = tf.train.Saver()

    lm = LstmLmInstance()
    qa = MpcmQaInstance()

    lm.load_from_chkpt(FLAGS.model_dir+'saved/lmtest')
    qa.load_from_chkpt(FLAGS.model_dir+'saved/qatest')

    lm_vocab=lm.vocab
    qa_vocab=qa.vocab

    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=mem_limit)
    with tf.Session(graph=model.graph, config=tf.ConfigProto(gpu_options=gpu_options)) as sess:
        if not os.path.exists(chkpt_path):
            exit('Checkpoint path doesnt exist! '+chkpt_path)
        summary_writer = tf.summary.FileWriter(FLAGS.log_dir+"eval/"+str(int(time.time())), sess.graph)

        saver.restore(sess, chkpt_path+ '/model.checkpoint')
        # print('Loading not implemented yet')
        # else:
        #     sess.run(tf.global_variables_initializer())
        #     sess.run(model.glove_init_ops)

        num_steps = len(dev_data)//FLAGS.batch_size

        # Initialise the dataset
        dev_data_source.initialise(dev_data)

        f1s=[]
        bleus=[]
        qa_scores=[]
        lm_scores=[]
        nlls=[]

        qgolds=[]
        qpreds=[]
        ctxts=[]
        answers=[]
        for e in range(1):
            for i in tqdm(range(num_steps), desc='Epoch '+str(e)):
                dev_batch, curr_batch_size = dev_data_source.get_batch()
                pred_batch,pred_ids,pred_lens,gold_batch, gold_lens,gold_ids,ctxt,ctxt_len,ans,ans_len,nll= sess.run([model.q_hat_beam_string, model.q_hat_beam_ids,model.q_hat_beam_lens,model.question_raw, model.question_length, model.question_ids, model.context_raw, model.context_length, model.answer_locs, model.answer_length, model.nll], feed_dict={model.input_batch: dev_batch ,model.is_training:False})

                for b, pred in enumerate(pred_batch):
                    pred_str = tokens_to_string(pred[:pred_lens[b]-1])
                    gold_str = tokens_to_string(gold_batch[b][:gold_lens[b]-1])
                    f1s.append(metrics.f1(gold_str, pred_str))
                    bleus.append(metrics.bleu(gold_str, pred_str))
                    qgolds.append(gold_str)
                    qpreds.append(pred_str)
                    ctxts.append(dev_batch[0][0][b].tolist())
                    answers.append(dev_batch[2][0][b].tolist())

                # qhat_for_lm = [preprocessing.lookup_vocab(q, lm_vocab, do_tokenise=False) for q in pred_batch.tolist()]
                # qgold_for_lm = [preprocessing.lookup_vocab(q, lm_vocab, do_tokenise=False) for q in gold_batch.tolist()]
                # qhat_for_qa = [preprocessing.lookup_vocab(q, qa_vocab, do_tokenise=False) for q in pred_batch.tolist()]
                # qgold_for_qa = [preprocessing.lookup_vocab(q, qa_vocab, do_tokenise=False) for q in dev_batch[1][0].tolist()]
                # ctxt_for_qa = [preprocessing.lookup_vocab(ctxt, qa_vocab, do_tokenise=False) for ctxt in dev_batch[0][0].tolist()]

                # get QA score
                qa_pred = qa.get_ans(ops.byte_token_array_to_str(dev_batch[0][0]), ops.byte_token_array_to_str(pred_batch))

                gold_str=[]
                pred_str=[]


                gold_str = ops.byte_token_array_to_str([dev_batch[2][0][b][:dev_batch[2][2][b]] for b in range(curr_batch_size)], is_array=False)
                # pred_str = ops.byte_token_array_to_str([dev_batch[0][0][b][qa_pred[b][0]:qa_pred[b][1]] for b in range(curr_batch_size)], is_array=False)


                qa_scores.extend([metrics.f1(gold_str[b], qa_pred[b]) for b in range(curr_batch_size)])
                lm_scores.extend(lm.get_seq_perplexity(ops.byte_token_array_to_str(pred_batch)).tolist()) # lower perplexity is better
                nlls.extend(nll.tolist())

                if i==0:
                    title=chkpt_path
                    out_str = output_eval(title,pred_batch,  pred_ids, pred_lens, gold_batch, gold_lens, ctxt, ctxt_len, ans, ans_len)
                    with open(FLAGS.log_dir+'out_eval_'+model_type+'.htm', 'w') as fp:
                        fp.write(out_str)

        res = list(zip(qpreds,qgolds,ctxts,answers))
        print(res)
        with open(FLAGS.log_dir+'out_eval_'+model_type+'.json', 'w') as fp:
            json.dump(res, fp)

        print("F1: ", np.mean(f1s))
        print("BLEU: ", np.mean(bleus))
        print("QA: ", np.mean(qa_scores))
        print("LM: ", np.mean(lm_scores))
        print("NLL: ", np.mean(nlls))

if __name__ == '__main__':
    tf.app.run()
