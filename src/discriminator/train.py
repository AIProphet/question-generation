import sys,json,math
sys.path.insert(0, "/Users/tom/Dropbox/msc-ml/project/src/")
sys.path.insert(0, "/cs/student/msc/ml/2017/thosking/dev/msc-project/src/")

import tensorflow as tf
import numpy as np

from instance import DiscriminatorInstance

import helpers.loader as loader

from tqdm import tqdm

def main(_):

    FLAGS = tf.app.flags.FLAGS



    # results=results[:32]



    # dev_ctxts, dev_qs,dev_ans,dev_ans_pos, dev_correct = zip(*squad_dev)

    positive_data=[]
    negative_data=[]

    if FLAGS.disc_trainongenerated is True:
        with open('./logs'+'/out_eval_'+ FLAGS.disc_modelslug +'.json') as f:
            results = json.load(f)
        for res in results:
            qpred,qgold,ctxt,ans_text,ans_pos =res
            positive_data.append( (ctxt, qgold, ans_text, ans_pos) )
            negative_data.append( (ctxt, qpred, ans_text, ans_pos) )

    if FLAGS.disc_trainonsquad is True:
        squad_v2 = loader.load_squad_triples(FLAGS.data_path, False, v2=True)
        for res in squad_v2:
            ctxt,q,ans_text,ans_pos,label =res
            if label is True:
                positive_data.append( (ctxt.lower(), q.lower(), ans_text.lower(), ans_pos) )
            else:
                negative_data.append( (ctxt.lower(), q.lower(), ans_text.lower(), ans_pos) )

    num_instances = min(len(negative_data), len(positive_data))

    disc = DiscriminatorInstance(trainable=True, log_slug=FLAGS.disc_modelslug)
    # disc.load_from_chkpt() # this loads the embeddings etc

    train_samples = math.floor(0.8*num_instances)
    dev_samples = math.floor(0.2*num_instances)

    positive_data_train = positive_data[:train_samples]
    negative_data_train = negative_data[:train_samples]
    positive_data_dev = positive_data[train_samples:]
    negative_data_dev = negative_data[train_samples:]

    num_steps_train = train_samples//FLAGS.batch_size
    num_steps_dev = dev_samples//FLAGS.batch_size
    num_steps_squad = num_steps_dev

    best_oos_nll=1e6

    for e in range(FLAGS.disc_num_epochs):
        np.random.shuffle(positive_data)
        np.random.shuffle(negative_data)
        # Train for one epoch
        for i in tqdm(range(num_steps_train), desc='Epoch '+str(e)):
            ixs = np.round(np.random.binomial(1,0.5,FLAGS.batch_size))
            # batch = train_data[i*FLAGS.batch_size:(i+1)*FLAGS.batch_size]
            batch = [negative_data_train[i*FLAGS.batch_size+j] if ix < 0.5 else positive_data_train[i*FLAGS.batch_size+j] for j,ix in enumerate(ixs.tolist())]
            ctxt,qbatch,ans_text,ans_pos = zip(*batch)

            # print(ans_text)
            # print(ans_pos)
            # print(ctxt)
            # exit()




            # +qpred[ix].replace("</Sent>","").replace("<PAD>","")
            qbatch = [q.replace(" </Sent>","").replace(" <PAD>","") for q in qbatch]
            # qbatch = ["fake " if ixs[ix] < 0.5 else "real " for ix in range(FLAGS.batch_size)]
            # print(qbatch, ixs)
            loss = disc.train_step(ctxt, qbatch, ans_text, ans_pos, ixs, (e*num_steps_train+i))

        dev_acc=[]
        dev_nll=[]
        for i in tqdm(range(num_steps_dev), desc='Epoch '+str(e) + " dev"):

            ixs = np.round(np.random.binomial(1,0.5,FLAGS.batch_size))
            batch = [negative_data_train[i*FLAGS.batch_size+j] if ix < 0.5 else positive_data_train[i*FLAGS.batch_size+j] for j,ix in enumerate(ixs.tolist())]
            ctxt,qbatch,ans_text,ans_pos = zip(*batch)

            qbatch = [q.replace(" </Sent>","").replace(" <PAD>","") for q in qbatch]

            pred = disc.get_pred(ctxt, qbatch, ans_text, ans_pos)
            nll = disc.get_nll(ctxt, qbatch, ans_text, ans_pos, ixs)
            acc = 1.0*np.equal(np.round(pred), ixs)
            dev_acc.extend(acc.tolist())
            dev_nll.extend(nll.tolist())

        accsummary = tf.Summary(value=[tf.Summary.Value(tag="dev_perf/acc",
                                         simple_value=np.mean(dev_acc))])
        nllsummary = tf.Summary(value=[tf.Summary.Value(tag="dev_perf/nll",
                                  simple_value=np.mean(dev_nll))])

        disc.summary_writer.add_summary(accsummary, global_step=(e+1)*num_steps_train)
        disc.summary_writer.add_summary(nllsummary, global_step=(e+1)*num_steps_train)

        print(np.mean(dev_acc))
        if np.mean(dev_nll) < best_oos_nll:
            best_oos_nll=np.mean(dev_nll)
            disc.save_to_chkpt(FLAGS.model_dir, e)
            print("New best NLL, saving")



if __name__ == "__main__":
    tf.app.run()
