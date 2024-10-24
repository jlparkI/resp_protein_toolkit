'''A CNN architecture for regression and classification. Adapted
from Microsoft's CARP which is adapted from ByteNet. Can use a
last-layer Gaussian process to improve uncertainty calibration
and provide variance estimates for regression if so specified
by user. This architecture is used when there is only one
sequence that is varied (e.g. an antibody that is mutated
while the target remains the same).'''
import numpy as np
import torch
import torch.nn.functional as F
from torch.nn.utils import spectral_norm as SpectralNorm
from ..classic_rffs import VanillaRFFLayer


class ConvLayer(torch.nn.Conv1d):
    """ A 1-dimensional convolution layer.

    Takes the same arguments as torch.nn.Conv1D, but applies automatic padding
    for convenience, and automatically performs transposition on inputs.

    
    """

    def __init__(self, in_channels: int, out_channels: int,
                 kernel_size: int, stride: int=1, dilation: int=1, groups: int=1,
                 bias: bool=True):
        """Class constructor.

        Args:
            param in_channels: input channels
            param out_channels: output channels
            param kernel_size: the kernel width
            param stride: filter shift
            param dilation: dilation factor
            param groups: perform depth-wise convolutions
            param bias: adds learnable bias to output
        """
        padding = dilation * (kernel_size - 1) // 2
        super().__init__(in_channels, out_channels, kernel_size,
                                            stride=stride, dilation=dilation,
                                            groups=groups, bias=bias, padding=padding)

    def forward(self, xdata):
        """Standard forward pass.
        Args:
            Input: (N, L, in_channels)
        Returns:
            Output: (N, L, out_channels)
        """
        return super().forward(xdata.transpose(1, 2)).transpose(1, 2)



class PositionFeedForward(torch.nn.Module):
    """A feed-forward layer for the bytenet block.

    Args:
        d_in: The input dimensionality.
        d_out: The output dimensionality.
        use_spectral_norm (bool): If True, use spectral norm on the weights.
    """

    def __init__(self, d_in, d_out, use_spectral_norm = False):
        super().__init__()
        if use_spectral_norm:
            self.conv = SpectralNorm(torch.nn.Conv1d(d_in, d_out, 1))
        else:
            self.conv = torch.nn.Conv1d(d_in, d_out, 1)
        self.factorized = False


    def forward(self, xdata):
        """The forward pass.

        Args:
            Input: (N, L, in_channels)
        Returns:
            Output: (N, L, out_channels)
        """
        return self.conv(xdata.transpose(1, 2)).transpose(1, 2)



class ByteNetBlock(torch.nn.Module):
    """Residual block from ByteNet paper (https://arxiv.org/abs/1610.10099).

    Args:
        d_in (int): the input dimensionality
        d_h (int): The within-block hidden dimensionality
        d_out (int): The output dimensionality
        kernel_size (int): the size of the convolution kernel
        dilation (int): The convolution kernel dilation
        groups (int): depth-wise convolutions (if desired)
        use_spectral_norm (bool): If True, use spectral norm on the weights.
    """

    def __init__(self, d_in, d_h, d_out, kernel_size, dilation=1, groups=1,
                 use_spectral_norm = False):
        super().__init__()
        if use_spectral_norm:
            self.conv = SpectralNorm(ConvLayer(d_h, d_h, kernel_size=kernel_size,
                                           dilation=dilation, groups=groups))
        else:
            self.conv = ConvLayer(d_h, d_h, kernel_size=kernel_size,
                                           dilation=dilation, groups=groups)

        layers1 = [
            torch.nn.LayerNorm(d_in),
            torch.nn.GELU(),
            PositionFeedForward(d_in, d_h, use_spectral_norm),
            torch.nn.LayerNorm(d_h),
            torch.nn.GELU()
        ]
        layers2 = [
            torch.nn.LayerNorm(d_h),
            torch.nn.GELU(),
            PositionFeedForward(d_h, d_out, use_spectral_norm),
        ]
        self.sequence1 = torch.nn.Sequential(*layers1)
        self.sequence2 = torch.nn.Sequential(*layers2)


    def forward(self, xdata):
        """
        Args:
            Input: (N, L, in_channels)
        Returns:
            Output: (N, L, out_channels)
        """
        return xdata + self.sequence2(
            self.conv(self.sequence1(xdata)))


class ByteNetPairedSeqs(torch.nn.Module):
    """A model for predicting the fitness of a given antibody-
    antigen pair using a series of ByteNet blocks. Note that it accepts
    two sets of sequences as input: the antigen sequence and the antibody
    sequence. Each of these is fed through its own series of ByteNet
    blocks, then at the end the representations of the two are
    merged.

    Args:
        input_dim (int): The expected dimensionality of the input, which is
            (N, L, input_dim).
        hidden_dim (int): The dimensions used inside the model.
        n_layers (int): The number of ByteNet blocks to use.
        kernel_size (int): The kernel width for ByteNet blocks.
        dil_factor (int): Used for calculating dilation factor, which increases on
            subsequent layers.
        rep_dim (int): At the end of the ByteNet blocks, the mean is taken across
            the tokens in each sequence to generate a representation. rep_dim
            determines the size of that representation.
        dropout (float): The level of dropout to apply.
        slim (bool): If True, use a smaller size within each ByteNet block.
        llgp (bool): If True, use a last-layer GP.
        antigen_dim: Either None or an int. If None, the antigen input is assumed
            to have the same dimensionality as the antibody.
        objective (str): Must be one of "regression", "binary_classifier",
            "multiclass".
        num_predicted_categories (int): The number of categories (i.e. possible values
            for y in output). Ignored unless objective is "multiclass".
    """
    def __init__(self, input_dim, hidden_dim, n_layers, kernel_size, dil_factor,
                rep_dim = 100, dropout = 0.0, slim = False, llgp = False, antigen_dim = None,
                objective = "regression", num_predicted_categories = 1):
        super().__init__()
        torch.manual_seed(123)
        torch.backends.cudnn.deterministic = True
        use_spectral_norm = llgp

        self.objective = objective
        if objective == "multiclass":
            nclasses = num_predicted_categories
            likelihood = "multiclass"
            if num_predicted_categories <= 2:
                raise RuntimeError("If running in multiclass mode, "
                        "num_predicted_categories must always be > 2. "
                        "If there are only two possible categories, "
                        "binary classification is more appropriate.")
        elif objective == "binary_classifier":
            nclasses = 1
            likelihood = "binary_logistic"
        elif objective == "regression":
            nclasses = 1
            likelihood = "Gaussian"
        else:
            raise RuntimeError("Unrecognized objective supplied.")

        if llgp:
            torch.cuda.manual_seed(123)
            torch.use_deterministic_algorithms(True)

        # Calculate the dilation factors for subsequent layers
        dil_log2 = int(np.log2(dil_factor)) + 1
        dilations = [2 ** (n % dil_log2) for n in range(n_layers)]
        d_h = hidden_dim
        if slim:
            d_h = d_h // 2

        self.adjuster = PositionFeedForward(input_dim, hidden_dim, use_spectral_norm)
        if antigen_dim is not None:
            self.antigen_adjuster = PositionFeedForward(antigen_dim, hidden_dim,
                                                        use_spectral_norm)
        else:
            self.antigen_adjuster = None

        antibody_layers = [
            ByteNetBlock(hidden_dim, d_h, hidden_dim, kernel_size, dilation=d,
                         use_spectral_norm = use_spectral_norm)
            for d in dilations
        ]
        self.antibody_layers = torch.nn.ModuleList(modules=antibody_layers)

        antigen_layers = [
            ByteNetBlock(hidden_dim, d_h, hidden_dim, kernel_size, dilation=d,
                         use_spectral_norm = use_spectral_norm)
            for d in dilations
        ]
        self.antigen_layers = torch.nn.ModuleList(modules=antigen_layers)

        self.down_adjuster = PositionFeedForward(hidden_dim, rep_dim,
                                            use_spectral_norm = use_spectral_norm)
        self.final_lnorm = torch.nn.LayerNorm(rep_dim)

        if llgp:
            self.out_layer = VanillaRFFLayer(in_features = rep_dim,
                        RFFs = 1024, out_targets = 1, gp_cov_momentum = 0.999,
                        gp_ridge_penalty = 1e-3, likelihood = likelihood,
                        random_seed = 123)
        else:
            if use_spectral_norm:
                self.out_layer = SpectralNorm(torch.nn.Linear(rep_dim, nclasses))
            else:
                self.out_layer = torch.nn.Linear(rep_dim, nclasses)

        self.dropout = dropout
        self.llgp = llgp


    def forward(self, x_antibody, update_precision = False, get_var = False):
        """
        Args:
            x_antibody (N, L, in_channels): -- the antibody sequence data
            update_precision (bool): Should be True during training, False
                otherwise.
            get_var (bool): If True, return estimated variance on predictions.
                Only available if 'llgp' in class constructor is True AND objective
                is regression. Otherwise, this option can still be passed but
                will be ignored.

        Returns:
            Output (tensor): -- Shape depends on objective. If regression or
                binary_classifier, shape will be (N). If multiclass, shape
                will be (N, num_predicted_classes) that was passed when the
                model was constructed.
            var (tensor): Only returned if get_var is True, objective is regression
                and model was initialized with llgp set to True. If returned, it
                is a tensor of shape (N).
        """
        x_antibody = self.adjuster(x_antibody)

        for layer in self.antibody_layers:
            x_antibody = layer(x_antibody)
            if self.dropout > 0.0 and self.training:
                x_antibody = F.dropout(x_antibody, self.dropout)

        x_antibody = self.down_adjuster(x_antibody)
        x_antibody = self.final_lnorm(torch.mean(x_antibody, dim=1))

        if self.objective == "regression":
            if self.llgp:
                if get_var:
                    preds, var = self.out_layer(x_antibody, get_var = get_var)
                    return preds.squeeze(1), var
                preds = self.out_layer(x_antibody, update_precision)
            else:
                preds = self.out_layer(x_antibody)
            return preds.squeeze(1)
        if self.objective == "binary_classifier":
            if self.llgp:
                preds = self.out_layer(x_antibody, update_precision)
            else:
                preds = self.out_layer(x_antibody)
            return F.sigmoid(preds.squeeze(1))
        if self.objective == "multiclass":
            if self.llgp:
                preds = self.out_layer(x_antibody, update_precision)
            else:
                preds = self.out_layer(x_antibody)
            return F.softmax(preds)

        # Double-check that the objective is correct to avoid weird
        # errors...
        raise RuntimeError("Model was initialized with an invalid task / objective.")





    def predict(self, x, get_var = False):
        """This function returns the predicted y-value for each
        datapoint. For convenience, it takes numpy arrays as input
        and returns numpy arrays as output. If you already have
        PyTorch tensors it may be slightly faster / more convenient
        to use forward instead of calling predict.

        Args:
            x (np.ndarray): The input antibody data.
            get_var (bool): If True, return estimated variance on predictions.
                Only available if 'llgp' in class constructor is True and the
                objective in the class constructor is "regression". Otherwise
                this argument is ignored.

        Returns:
            scores (np.ndarray): If class objective is "regression" or
                "binary_classifier", this is of shape (N). If "multiclass",
                this is of shape (N, num_predicted_classes) from the
                class constructor.
            var (np.ndarray): Only returned if get_var is True, llgp in
                the class constructor is True and the objective is "regression".
                If returned, is of shape (N).
        """
        with torch.no_grad():
            self.eval()
            x = torch.from_numpy(x).float()
            if next(self.parameters()).is_cuda:
                x = x.cuda()
            if self.llgp and get_var and self.objective == "regression":
                preds, var = self.forward(x, get_var = get_var)
                return preds.cpu().numpy(), var.cpu().numpy()
            return self.forward(x).cpu().numpy()
