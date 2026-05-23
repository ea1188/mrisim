import numpy as np

def image_to_kspace(image):
    kspace = np.fft.fftshift(np.fft.fft2(np.fft.ifftshift(image)))
    return kspace

def kspace_to_image(kspace):
    image = np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(kspace))))
    return image

def apply_matrix_size(kspace_full, target_matrix):
    full_size = kspace_full.shape[0]
    if target_matrix >= full_size:
        return kspace_full
    start = (full_size - target_matrix) // 2
    end = start + target_matrix
    cropped = kspace_full[start:end, start:end]
    return cropped

def zero_fill_resize(kspace_small, target_size):
    current_size = kspace_small.shape[0]
    if current_size >= target_size:
        return kspace_to_image(kspace_small)
    padded = np.zeros((target_size, target_size), dtype=complex)
    start = (target_size - current_size) // 2
    end = start + current_size
    padded[start:end, start:end] = kspace_small
    image = np.abs(np.fft.fftshift(np.fft.ifft2(np.fft.ifftshift(padded))))
    image = image * (target_size / current_size) ** 2
    return image

def apply_aliasing(image, fov_fraction):
    if fov_fraction >= 1.0:
        return image
    size = image.shape[0]
    new_fov_pixels = int(size * fov_fraction)
    if new_fov_pixels < 10:
        new_fov_pixels = 10
    result = np.zeros((new_fov_pixels, new_fov_pixels))
    for i in range(size):
        for j in range(size):
            wi = i % new_fov_pixels
            wj = j % new_fov_pixels
            result[wi, wj] += image[i, j]
    return result

def simulate_acquisition(image, matrix_size, fov_fraction=1.0):
    kspace_full = image_to_kspace(image)
    kspace_acquired = apply_matrix_size(kspace_full, matrix_size)
    if matrix_size < image.shape[0]:
        reconstructed = zero_fill_resize(kspace_acquired, image.shape[0])
    else:
        reconstructed = kspace_to_image(kspace_acquired)
    if fov_fraction < 1.0:
        reconstructed = apply_aliasing(reconstructed, fov_fraction)
        from scipy.ndimage import zoom
        scale = image.shape[0] / reconstructed.shape[0]
        reconstructed = zoom(reconstructed, scale, order=1)
    return reconstructed, kspace_acquired

def get_kspace_display(kspace):
    magnitude = np.abs(kspace)
    display = np.log1p(magnitude)
    return display

if __name__ == "__main__":
    from phantom import create_brain_phantom, TISSUE_PROPERTIES
    from signal_engine import spin_echo_signal
    phantom = create_brain_phantom(256)
    image = np.zeros_like(phantom, dtype=float)
    for label, props in TISSUE_PROPERTIES.items():
        mask = phantom == label
        sig = spin_echo_signal(props["T1"], props["T2"], props["PD"], 500, 15)
        image[mask] = sig
    for matrix in [256, 128, 64]:
        recon, ks = simulate_acquisition(image, matrix)
        print(f"Matrix {matrix}: recon shape={recon.shape}, max signal={recon.max():.4f}")
    print("k-space module working.")