import os,time, json

# CUDA config
os.environ["CUDA_VISIBLE_DEVICES"]="3"
mem_limit=0.5

import tensorflow as tf
import numpy as np
import helpers.loader as loader
import helpers.metrics as metrics
from helpers.output import output_pretty, tokens_to_string
from tqdm import tqdm

from seq2seq_model import Seq2SeqModel

import flags


# config
# tf.app.flags.DEFINE_boolean("train", True, "Training mode?")
# tf.app.flags.DEFINE_integer("eval_freq", 100, "Evaluate the model after this many steps")
# tf.app.flags.DEFINE_integer("num_epochs", 20, "Train the model for this many epochs")
# tf.app.flags.DEFINE_integer("batch_size", 16, "Batch size")
# tf.app.flags.DEFINE_string("data_path", '../data/', "Path to dataset")
# tf.app.flags.DEFINE_string("log_dir", './logs/', "Path to logs")
# tf.app.flags.DEFINE_string("model_dir", './models/', "Path to checkpoints")
#
# tf.app.flags.DEFINE_boolean("use_gpu", False, "Is a GPU available on this system?")
#
# # hyperparams - these should probably be within the model?
# tf.app.flags.DEFINE_integer("embedding_size", 200, "Dimensionality to use for learned word embeddings")
# tf.app.flags.DEFINE_integer("context_encoder_units", 768, "Number of hidden units for context encoder (ie 1st stage)")
# tf.app.flags.DEFINE_integer("answer_encoder_units", 768, "Number of hidden units for answer encoder (ie 2nd stage)")
# tf.app.flags.DEFINE_integer("decoder_units", 768, "Number of hidden units for decoder")
# tf.app.flags.DEFINE_integer("vocab_size", 2000, "Shortlist vocab size")
# tf.app.flags.DEFINE_float("learning_rate", 2e-4, "Optimizer learning rate")
# tf.app.flags.DEFINE_float("dropout_rate", 0.3, "Dropout probability")



FLAGS = tf.app.flags.FLAGS

# FLAGS.batch_size = 1

def main(_):
    # load dataset
    train_data = loader.load_squad_triples(FLAGS.data_path, False)
    dev_data = loader.load_squad_triples(FLAGS.data_path, True)[:1500]

    print('Loaded SQuAD with ',len(train_data),' triples')
    print('Loaded SQuAD dev set with ',len(dev_data),' triples')
    train_contexts, train_qs, train_as,train_a_pos = zip(*train_data)
    dev_contexts, dev_qs, dev_as, dev_a_pos = zip(*dev_data)
    vocab = loader.get_vocab(train_contexts, tf.app.flags.FLAGS.vocab_size)

    # Create model

    model = Seq2SeqModel(vocab, batch_size=FLAGS.batch_size, training_mode=False)
    saver = tf.train.Saver()

    chkpt_path = FLAGS.model_dir+'latest'

    gpu_options = tf.GPUOptions(per_process_gpu_memory_fraction=mem_limit)
    with tf.Session(config=tf.ConfigProto(gpu_options=gpu_options)) as sess:
        if not os.path.exists(chkpt_path):
            os.makedirs(chkpt_path)
        summary_writer = tf.summary.FileWriter(FLAGS.log_dir+str(int(time.time())), sess.graph)

        saver.restore(sess, chkpt_path+ '/model.checkpoint')
        # print('Loading not implemented yet')
        # else:
        #     sess.run(tf.global_variables_initializer())
        #     sess.run(model.glove_init_ops)

        num_steps = len(dev_data)//FLAGS.batch_size

        # Initialise the dataset
        sess.run(model.iterator.initializer, feed_dict={model.context_ph: dev_contexts,
                                          model.qs_ph: dev_qs, model.as_ph: dev_as, model.a_pos_ph: dev_a_pos})

        f1s=[]
        bleus=[]
        for e in range(1):
            for i in tqdm(range(num_steps), desc='Epoch '+str(e)):
                ops = [model.q_hat_string, model.q_gold, model.context_raw]
                res= sess.run(ops, feed_dict={model.is_training:False})

                if i < 5:
                    print("Pred: ", tokens_to_string(res[0][0].tolist()))
                    print("Gold: ", tokens_to_string(res[1][0].tolist()))
                    print('***')


                for b, pred in enumerate(res[0]):
                    pred_str = tokens_to_string(pred)
                    gold_str = tokens_to_string(res[1][b])
                    f1s.append(metrics.f1(gold_str, pred_str))
                    bleus.append(metrics.bleu(gold_str, pred_str))

        print("F1: ", np.mean(f1s))
        print("BLEU: ", np.mean(bleus))

if __name__ == '__main__':
    tf.app.run()
