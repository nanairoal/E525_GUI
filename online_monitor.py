import sys
from multiprocessing import Process
import time
import signal
import os
from event_monitor import *
import matplotlib.pyplot as plt 
from matplotlib.widgets import RadioButtons


newestDir = ''
currentProcs = {}
rawext = '.raw'
conf = ('ch0.conf', 'ch1.conf', 'ch2.conf', 'ch3.conf', 'ch4.conf', 'ch5.conf', 'ch6.conf', 'ch7.conf')

#user variable
enable_ch = (3,5,7)
#monitorDir = '/home/assy2/Work/E525/data/raw'
monitorDir = './data'

if (len(enable_ch) > 3) and (len(enable_ch) <= 0):
    print('Length of the enable_ch is out of the range')
    print(enable_ch.len(enable_ch))
    exit(-1)

if not os.path.isdir(monitorDir):
    print(monitorDir + ' does not exist')
    exit(-1)

#create figure
fig_width = 12.8
fig_height = 4.8*len(enable_ch)
fig = plt.figure(1,figsize=(fig_width, fig_height))
fig.canvas.set_window_title("E525 online monitor")

hist_width = 0.38
ax_height = 0.25
radio_width = 0.1
radio_height = 0.1
left = 0.01
left_ene = radio_width + left + 0.05
left_time = left_ene + hist_width + 0.05
ax_rect_list = []
bottom = 0.06
bottom_rad1 = bottom + 0.15
bottom_rad2 = bottom + 0.01
i = len(enable_ch)
while i > 0:
    i -= 1
    ax_rect_list.insert(0,[[left, bottom_rad1, radio_width, radio_height],
                          [left, bottom_rad2, radio_width, radio_height],
                          [left_ene, bottom, hist_width, ax_height],
                          [left_time, bottom, hist_width, ax_height]])

    bottom += ax_height + 0.06
    bottom_rad1 += ax_height + 0.06
    bottom_rad2 += ax_height + 0.06


def getNewestDir(dirlist):
    if len(dirlist) == 0:
        return None
    
    firstdir = None

    for dir in dirlist:
        if os.path.isdir(monitorDir +'/' +dir):
            firstdir = dir
            break
    
    if firstdir is None:
        return None

    dirTime1 = os.path.getctime(monitorDir +'/'+ firstdir)
    newestdir = firstdir

    for dir in dirlist:
        if os.path.isfile(monitorDir +'/'+ dir):
            continue

        dirTime2 = os.path.getctime(monitorDir +'/'+ dir)
        if dirTime2 > dirTime1:
            dirTime1 = dirTime2
            newestdir = dir

    return newestdir

def terminateProcesses():
    for proc in currentProcs.values():
        proc.terminate()
    currentProcs.clear()
    fig.clear()

def getRawFiles(rawdir):
    rawfiles = []
    for file in os.listdir(rawdir):
        base,ext = os.path.splitext(file)
        if ext == rawext:
            rawfiles.append(monitorDir +'/'+ newestDir + base + ext)
    return rawfiles


def handler_terminate(signal, frame):
    print('termiate monitor')
    terminateProcesses()
    sys.exit(0)


signal.signal(signal.SIGINT, handler_terminate)
print ('started the online monitor')
print ('Raw data directory is ' + monitorDir) 
newestDir = ''
def monitor_Dir(ax):

    global newestDir

    newestDir2 = getNewestDir(os.listdir(monitorDir))
    
    for raw in currentProcs:
        currentProcs[raw].update_monitor()

    if newestDir2 is None:
        return

    newestDir2 += '/'

    if newestDir != newestDir2:
        terminateProcesses()
        currentProcs.clear()
        newestDir = newestDir2
        fig.canvas.set_window_title("E525 online montor : " + newestDir)
        print('monitoring ' + newestDir)

    rawFiles = getRawFiles(monitorDir +'/'+ newestDir)

    for raw in rawFiles:
        for i, ch in enumerate(enable_ch):
            if 'ch' + str(ch) in raw:
                if not raw in currentProcs:
                    monitor = Event_monitor(fig, ax_rect_list[i], raw, 'monitor_conf/'+conf[ch])
                    monitor.start()
                    currentProcs[raw] = monitor

timer = fig.canvas.new_timer(interval=500)
timer.add_callback(monitor_Dir,None)
timer.start()
plt.show()
