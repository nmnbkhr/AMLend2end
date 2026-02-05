"""
WGAN-GP Anomaly Detector — PyTorch port of adversarialaml/gan_enc_ano.py

Architecture:
  Discriminator: input_dim → bottleneck dense → 1 (Wasserstein critic)
  Generator:     latent_dim → expanding dense → input_dim
  Encoder:       input_dim → bottleneck dense → latent_dim

Anomaly score: ||x - G(E(x))||^2  (reconstruction error through encoder→generator)

Reference: https://arxiv.org/pdf/1905.11034.pdf
"""

import torch
import torch.nn as nn
import torch.autograd as autograd


# ---------------------------------------------------------------------------
# Activation helper
# ---------------------------------------------------------------------------
def _get_activation(name: str) -> nn.Module:
    activations = {
        "relu": nn.ReLU(),
        "leaky_relu": nn.LeakyReLU(0.2),
        "selu": nn.SELU(),
        "tanh": nn.Tanh(),
        "linear": nn.Identity(),
    }
    return activations.get(name, nn.LeakyReLU(0.2))


# ---------------------------------------------------------------------------
# Network builder
# ---------------------------------------------------------------------------
def _build_layers(dims, activation="leaky_relu", dropout_rate=0.0,
                  batch_norm=True, final_activation=None):
    """Build a sequential stack of Linear → BatchNorm → Activation → Dropout."""
    layers = []
    for i in range(len(dims) - 1):
        layers.append(nn.Linear(dims[i], dims[i + 1]))
        is_last = (i == len(dims) - 2)
        if is_last:
            if final_activation is not None:
                layers.append(_get_activation(final_activation))
        else:
            if batch_norm:
                layers.append(nn.BatchNorm1d(dims[i + 1]))
            layers.append(_get_activation(activation))
            if dropout_rate > 0:
                layers.append(nn.Dropout(dropout_rate))
    return nn.Sequential(*layers)


# ---------------------------------------------------------------------------
# Discriminator  (Wasserstein critic — no sigmoid on output)
# ---------------------------------------------------------------------------
class Discriminator(nn.Module):
    """Bottleneck architecture: dims shrink toward output=1."""

    def __init__(self, input_dim, hidden_dim=64, n_layers=3,
                 activation="leaky_relu", dropout_rate=0.0, batch_norm=False):
        super().__init__()
        dims = [input_dim]
        d = hidden_dim
        for _ in range(n_layers):
            dims.append(d)
            d = max(d // 2, 8)
        dims.append(1)
        # WGAN-GP: no batch norm in discriminator (standard practice)
        self.net = _build_layers(dims, activation, dropout_rate,
                                 batch_norm=batch_norm, final_activation=None)

    def forward(self, x):
        return self.net(x)


# ---------------------------------------------------------------------------
# Generator  (latent → data space)
# ---------------------------------------------------------------------------
class Generator(nn.Module):
    """Expanding architecture: dims grow from latent_dim toward output_dim."""

    def __init__(self, latent_dim, output_dim, hidden_dim=32, n_layers=3,
                 activation="leaky_relu", dropout_rate=0.0, batch_norm=True):
        super().__init__()
        dims = [latent_dim]
        d = hidden_dim
        for _ in range(n_layers):
            dims.append(d)
            d = min(d * 2, output_dim)
        dims.append(output_dim)
        self.net = _build_layers(dims, activation, dropout_rate,
                                 batch_norm=batch_norm, final_activation=None)

    def forward(self, z):
        return self.net(z)


# ---------------------------------------------------------------------------
# Encoder  (data → latent space)
# ---------------------------------------------------------------------------
class Encoder(nn.Module):
    """Bottleneck architecture: dims shrink toward latent_dim."""

    def __init__(self, input_dim, latent_dim, hidden_dim=64, n_layers=3,
                 activation="leaky_relu", dropout_rate=0.0, batch_norm=True):
        super().__init__()
        dims = [input_dim]
        d = hidden_dim
        for _ in range(n_layers):
            dims.append(d)
            d = max(d // 2, latent_dim)
        dims.append(latent_dim)
        self.net = _build_layers(dims, activation, dropout_rate,
                                 batch_norm=batch_norm, final_activation=None)

    def forward(self, x):
        return self.net(x)


# ---------------------------------------------------------------------------
# Gradient Penalty  (WGAN-GP)
# ---------------------------------------------------------------------------
def gradient_penalty(discriminator, real_data, fake_data, device):
    """
    Compute gradient penalty for WGAN-GP.

    Interpolates between real and fake, computes D gradient norm,
    penalises deviation from 1.
    """
    batch_size = real_data.size(0)
    alpha = torch.rand(batch_size, 1, device=device)
    interpolated = (alpha * real_data + (1 - alpha) * fake_data).requires_grad_(True)

    d_interpolated = discriminator(interpolated)

    gradients = autograd.grad(
        outputs=d_interpolated,
        inputs=interpolated,
        grad_outputs=torch.ones_like(d_interpolated),
        create_graph=True,
        retain_graph=True,
    )[0]

    grad_norm = gradients.norm(2, dim=1)
    gp = ((grad_norm - 1.0) ** 2).mean()
    return gp


# ---------------------------------------------------------------------------
# Anomaly score
# ---------------------------------------------------------------------------
@torch.no_grad()
def anomaly_score(x, encoder, generator):
    """
    Anomaly score = ||x - G(E(x))||^2  per sample.

    High score → anomalous (can't reconstruct well).
    Low score  → normal (in-distribution).
    """
    encoder.eval()
    generator.eval()
    z = encoder(x)
    x_recon = generator(z)
    return torch.sum((x - x_recon) ** 2, dim=1)
