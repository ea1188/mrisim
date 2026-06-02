import numpy as np
import matplotlib.pyplot as plt
from signal_engine import spin_echo_signal, gradient_echo_signal
from phantom import create_brain_phantom, TISSUE_PROPERTIES


def simulate_spin_echo(phantom: np.ndarray, TR: float, TE: float) -> np.ndarray:
    """Generate a simulated spin echo image from phantom."""
    image = np.zeros_like(phantom, dtype=float)
    for label, props in TISSUE_PROPERTIES.items():
        mask = phantom == label
        signal = spin_echo_signal(props["T1"], props["T2"], props["PD"], TR, TE)
        image[mask] = signal
    return image

def simulate_gradient_echo(phantom: np.ndarray, TR: float, TE: float, flip_angle: float) -> np.ndarray:
    """Generate a simulated gradient echo image from phantom."""
    # Use T2* approximation: T2* ~ T2 * 0.6 for brain at 3T
    image = np.zeros_like(phantom, dtype=float)
    for label, props in TISSUE_PROPERTIES.items():
        mask = phantom == label
        T2star = props["T2"] * 0.6
        signal = gradient_echo_signal(props["T1"], T2star, props["PD"], TR, TE, flip_angle)
        image[mask] = signal
    return image

def add_noise(
    image: np.ndarray,
    snr_level: float = 30,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Add Rician noise to simulate realistic MRI noise."""
    if rng is None:
        rng = np.random.default_rng()
    sigma = np.max(image) / snr_level
    noise_real = rng.normal(0, sigma, image.shape)
    noise_imag = rng.normal(0, sigma, image.shape)
    return np.sqrt((image + noise_real) ** 2 + noise_imag ** 2)

def display_image(image: np.ndarray, title: str = "Simulated MRI", save_path: str | None = None) -> None:
    """Display the simulated image."""
    plt.figure(figsize=(8, 8))
    plt.imshow(image, cmap='gray', origin='upper')
    plt.title(title, fontsize=14)
    plt.colorbar(label='Signal Intensity')
    plt.axis('off')
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"Saved: {save_path}")
    plt.show()

if __name__ == "__main__":
    # Create phantom
    phantom = create_brain_phantom(256)
    
    # Simulate T1-weighted spin echo
    TR, TE = 500, 15
    image = simulate_spin_echo(phantom, TR, TE)
    image_noisy = add_noise(image, snr_level=35)
    display_image(image_noisy, f"Spin Echo: TR={TR}ms, TE={TE}ms (T1-weighted)")
