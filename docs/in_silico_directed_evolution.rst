What is in silico directed evolution
======================================

The computational portion of the RESP pipeline may be divided into
three steps:

#. Step 1. Prepare the experimental data for analysis (quality filter
   raw reads, translate to amino acid sequences, number or align if
   necessary).
#. Step 2. Fit an uncertainty-aware model and ensure that performance
   is sufficient (e.g. using cross-validation).
#. Step 3. Run *in silico* directed evolution, using the uncertainty-aware
   model to identify candidate sequences predicted to be tight binders or
   exhibit high activity.
#. Step 4. Filter the accepted sequences from the *in silico* search for
   humanness, developability and other desired properties.

Step 1 tends to be fairly problem-specific -- it may depend, for example,
on how the experiment was set up and the sequencing technology -- and so
tools for this step are not provided here.

There are a broad range of options available for Step 2. Of these, we've found
CNNs with a last-layer GP (an SNGP model) and approximate Gaussian processes
`to work very well <https://www.biorxiv.org/content/10.1101/2024.07.30.605700v1>`_,
although we've used variational Bayesian NNs
`before as well. <https://www.nature.com/articles/s41467-023-36028-8)>`_ To learn
how to fit an approximate GP to sequence data, see the
`xGPR library documentation <https://xgpr.readthedocs.io/en/latest/>`_. We'll
eventually provide support for training vBNNs and SNGP here, although for now
to train these models see `this example <https://github.com/Wang-lab-UCSD/RESP>`_
and `this example <https://github.com/Wang-lab-UCSD/RESP2>`_.

Step 4 requires models with high accuracy for predicting immunogenicity / humanness
and other key developability properties (e.g. stability). For humanness, we've
released a model in `the AntPack library
<https://antpack.readthedocs.io/en/latest/index.html>`_ that
`achieves excellent performance <https://academic.oup.com/bioinformatics/article/40/5/btae278/7656770>`_.

This leaves step 3, where we search sequence space for new candidates with predicted high
binding. It's not necessary to use generative models for this step -- indeed, we've found
this merely substitutes a black-box alternative for methods like genetic
algorithms or simulated annealing. Our preferred alternative here is *in silico* directed
evolution: a modified variant on simulated annealing in which we introduce and score mutations
into a starting wild-type sequence. For details, `see this paper <https://www.nature.com/articles/s41467-023-36028-8>`_.

The `resp_protein_toolkit` provides support for conducting an in silico directed evolution
search using a trained uncertainty-aware model. Uncertainty is key here: if the model is
not uncertainty-aware, we can veer into poorly-mapped regions of sequence space that are
not represented in the training data. By restricting our search to high-confidence candidates,
we can minimize the number of experimental evaluations needed for success.

How to run in silico directed evolution
==========================================
First, create a Python class that exposes a function called :code:`predict`. It should take

