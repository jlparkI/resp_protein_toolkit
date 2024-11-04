Built-in models for protein sequence data / fitness landscapes
===============================================================

The `resp_protein_toolkit` contains a couple of built-in deep learning
models that are easy to use for modeling protein fitness landscapes.
Currently the available built-in models are based on Microsoft's ByteNet,
but are adapted so that they can be made uncertainty-aware using the
VanillaRFFs layer also available in this package. You do not have to
use these models and can substitute another uncertainty-aware model of
your choosing when using the RESP *in silico* directed evolution
also available in this package if desired.

First, let's look briefly at each model, and then we'll look at an example
of how to train one of these models on the sequences in a csv file, then
use the resulting model to generate new candidate sequences through *in silico*
directed evolution.

.. autoclass:: resp_protein_toolkit.ByteNetSingleSeq
   :special-members: __init__
   :members: forward, predict

.. autoclass:: resp_protein_toolkit.ByteNetPairedSeqs
   :special-members: __init__
   :members: forward, predict


To train these models, it's typical to pass one of them together with
training settings (learning rate, learning rate scheduler, selected
optimizer etc.) to a function that will train the model for some set
number of epochs (say 1 or 2), then calculate some performance metric
on the training and test set.

We could encode all of the sequences first and save them on disk as
numpy / pytorch arrays, and for some tasks that may be more convenient.
In this case, however, we'll encode them on the fly. This has the advantage
that we only need a (gzipped) csv or fasta file as input, so very little
disk space is consumed, and we are one-hot encoding the sequences using a tool
in this package, which is very fast.

For this example, we'll assume you have a saved gzipped csv file called
"input_data.csv.gz" in the same directory as your python script and
that you are trying to model a binary classification problem where some
sequences are classified as binders (class 1) and others as nonbinders
(class 0). The first column of the csv file contains the sequence, the
second contains the class label. We load sequences in minibatches as
illustrated.

The details of learning rate, learning rate scheduler,
optimizer etc. may need to be changed depending on your problem; it's
usually a good idea to check performance on a validation set and adjust
as needed. If you're trying to predict a real value (say measured Kd),
you'll need to use a regression objective instead of course::

  
