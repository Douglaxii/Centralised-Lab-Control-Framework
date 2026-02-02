# Calculates exposure times for given ROIs and different settings
# formula taken from the datasheet chapter 11-1-3

import numpy as np
import matplotlib.pyplot as plt

# USB mode
# interface band width
BW = [167473152, 223297536, 334946304] # 16bit, 12bit, 8bit
Exp = 7.2e-6 # time between 7.2µs and 273.7152 ms
H = 7.2e-6 # time between 7.2µs and 237.6
# the manual uses minimal times for Exp1 and H to get maximum fps

Hn = 4096 # max 2304
Vn = 2304 # max 2304

def Exp2(Exp1, H):
    return np.round(Exp1/H)

def Vn2(Vn):
    return (Vn/2) + 5

def Vn3(Hn, Vn, BW, H):
    return np.round(Hn*(Vn + 6)/BW/H)

def max_framerate_USB_free(Hn, Vn, Exp1, H, BW):
    exp2 = Exp2(Exp1, H)
    vn2 = Vn2(Vn)
    vn3 = Vn3(Hn, Vn, BW, H)
    print(exp2, vn2, vn3)

    if exp2 + vn2 + 2 < vn3:
        return 1/vn3/H
    else:
        return 1/(exp2 + vn2 +2) / H

def max_framerate_USB_edge(Hn, Vn, Exp1, H, BW):
    exp2 = Exp2(Exp1, H)
    vn2 = Vn2(Vn)
    vn3 = Vn3(Hn, Vn, BW, H)
    print(exp2, vn2, vn3)

    return np.where(
        exp2 + vn2 + 2 < vn3,
        1 / (vn3 + 1) / H,
        1 / (exp2 + vn2 + 3) / H
    )

def max_framerate_CoaX_free(Vn, Exp1, H):
    exp2 = Exp2(Exp1, H)
    vn2 = Vn2(Vn)

    return 1/(vn2 + exp2 +2) / H

def max_framerate_CoaX_edge(Vn, Exp1, H):
    exp2 = Exp2(Exp1, H)
    vn2 = Vn2(Vn)

    return 1/(vn2 + exp2 +3) / H


fps_free = max_framerate_USB_free(Hn, Vn, Exp, H, BW[0])
fps_edge = max_framerate_USB_edge(Hn, Vn, Exp, H, BW[0])
fps_coax_free = max_framerate_CoaX_free(Vn, Exp, H)
fps_coax_edge = max_framerate_CoaX_edge(Vn, Exp, H)

print(f"Sensor matrix (HxV): {Hn}x{Vn}")
print(f"Free running mode: {fps_free} fps, {1/fps_free} s")
print(f"Edge trigger: {fps_edge} fps, {1/fps_edge} s")
print(f"Free running mode CoaX: {fps_coax_free} fps, {1/fps_coax_free} s")
print(f"Edge trigger CoaX: {fps_coax_edge} fps, {1/fps_coax_edge} s")

# plot fps data as a function of ROI size
x, y = np.meshgrid(np.arange(0, Hn), np.arange(0, Vn))
print(f"x: {x}")
x_sub = x[0:256, 0:1024]
y_sub = y[0:256, 0:1024]
z = max_framerate_USB_edge(x_sub, y_sub, Exp, H, BW[0])
# z_sub = z[256:Vn, 512:Hn]

z_min, z_max = np.min(z), np.max(z)
print(z)
fig, ax = plt.subplots()
# good colors: tab20c, viridis, hsv, gist_ncar, nipy_spectral
c = ax.pcolormesh(x_sub, y_sub, z, cmap='nipy_spectral', vmin=z_min, vmax=z_max)
# ax.set_title('Maximum fps as a function of ROI dimensions')
# ax.set_xlim(512, 4096)
# ax.set_ylim(256, 2304)
ax.set_xlabel("CCD Pixelzeile $n_h$")
ax.set_ylabel("CCD Pixelspalte $n_v$")
cbar=fig.colorbar(c, ax=ax)
cbar.ax.set_ylabel("Maximale CCD Auslesefrequenz f(FPS)")
plt.show()