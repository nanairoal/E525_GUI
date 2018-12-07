import numpy as np
import matplotlib.pyplot as plt
import matplotlib.path as path
import matplotlib.patches as patches
from   matplotlib.widgets import RadioButtons
from matplotlib.axes import Axes
import struct
import time
import os
import re
import tkinter
from multiprocessing import Process, Queue
from queue import Empty

class Realtime_histogram(Axes):
    def __init__(self, fig, rect, bin, xmin, xmax, auto_range):
        super().__init__(fig,rect = rect)
        self.NBIN = bin
        self.xmax = xmax
        self.xmin = xmin
        self.AUTORANGE = auto_range
        self.events = np.empty(0)

        n,bins = np.histogram(np.zeros(1),self.NBIN, range=(xmin,xmax))
        self.left = np.array(bins[:-1])
        self.right = np.array(bins[1:])
        self.bottom = np.zeros(self.NBIN)
        self.top = self.bottom + n

        nverts = self.NBIN * (1 + 3 + 1)
        self.verts = np.zeros((nverts,2))
        codes = np.ones(nverts,int) * path.Path.LINETO
        codes[0::5] = path.Path.MOVETO
        codes[4::5] = path.Path.CLOSEPOLY
        self.verts[0::5, 0] = self.left
        self.verts[0::5, 1] = self.bottom
        self.verts[1::5, 0] = self.left
        self.verts[1::5, 1] = self.top
        self.verts[2::5, 0] = self.right
        self.verts[2::5, 1] = self.top
        self.verts[3::5, 0] = self.right
        self.verts[3::5, 1] = self.bottom

        barpath = path.Path(self.verts, codes)
        patch = patches.PathPatch(barpath,edgecolor='none')
        super().add_patch(patch)
        super().set_xlim(self.left[0], self.right[-1])
        super().set_ylim(self.bottom.min(),self.top.max())


    def change_scale(self,label):
        if label == 'Log':
            subticks = [1,2,3,4,5,6,7,8,9]
            self.set_yscale('symlog',basey = 10 ,nonposy="mask",subsy=subticks)
        if label == 'Linear':
            self.set_yscale('linear')

        self.figure.canvas.draw()

            
    def __update_xlim(self,bins):        
        self.left = np.array(bins[:-1])
        self.right = np.array(bins[1:])
        self.verts[0::5, 0] = self.left
        self.verts[0::5, 1] = self.bottom
        self.verts[1::5, 0] = self.left
        self.verts[1::5, 1] = self.top
        self.verts[2::5, 0] = self.right
        self.verts[2::5, 1] = self.top
        self.verts[3::5, 0] = self.right
        self.verts[3::5, 1] = self.bottom


    def update_hist(self,sub_events):
        if sub_events.size == 0:
            return
        
        if self.AUTORANGE:
            change = False
            if self.xmax < sub_events.max():
                self.xmax = sub_events.max()
                change = True
            if self.xmin > sub_events.min():
                self.xmin = sub_events.min()
                change = True
            
            if change:
                n, bins = np.histogram(self.events, self.NBIN, range=(self.xmin, self.xmax))
                self.__update_xlim(bins)
                super().set_xlim((self.xmin,self.xmax))
            else:
                n, bins = np.histogram(sub_events, self.NBIN, range=(self.xmin, self.xmax))
        else:
            n,bins = np.histogram(sub_events, self.NBIN, range=(self.xmin, self.xmax))

        self.top = self.bottom + n
        self.verts[1::5,1] += self.top
        self.verts[2::5,1] += self.top
        super().set_ylim(0,self.verts[1::5,1].max())


class Event_monitor:
    def __init__(self, fig, ax_rects, rawfile, conf):
        self.SMP = 2050
        self.BASE = 8190
        self.NBIN = 1000
        self.AUTORANGE = True
        self.P = [0,1,0]
        self.XLABEL = 'Integrated Pulse'
        self.ENABLE = True
        self.xlim = [-5000,600000]
        self.TITLE = 'Test Title'
        self.RF = ''
        self.RF_th = 1000
        self.PULSE_th = 80
        self.TIME_MAX = self.SMP
        self.DISPLAY_EXTRA_TIME = True
        self.POLAR = False
        self.RF_BASE = self.BASE
        self.SKIP_BASE = -1
        self.CALC_BASE = False
        
        self.rawfile = rawfile
        self.f_hist = open(rawfile,'rb')
        self.events = [np.empty(0,dtype='f8'),np.empty(0,dtype='f8')]
        self.filesize = 0

        try:
            with open(conf) as conf_file:
                for line in conf_file.readlines():
                    self.__readConfig(line)
        except IOError:
            print(conf + " cannot be opend.")
        
        self.format = ''
        i = 0
        while i < self.SMP:
            self.format += 'i'
            i+= 1
            
        self.__setupAxes(fig, ax_rects)

    
    def start(self):
        self.q = Queue()
        self.p = Process(target=self.__update_events)
        self.p.start()


    def __setupAxes(self, fig, ax_rects):
        ax_radio1 = fig.add_axes(ax_rects[0],facecolor='lightgoldenrodyellow') 
        ax_radio2 = fig.add_axes(ax_rects[1],facecolor='lightgoldenrodyellow')
        self.ax_ene = Realtime_histogram(fig,ax_rects[2],self.NBIN,self.xlim[0],self.xlim[1],self.AUTORANGE)
        self.ax_time = Realtime_histogram(fig,ax_rects[3],self.NBIN,0,self.SMP,self.AUTORANGE)
        fig.add_axes(self.ax_ene)
        fig.add_axes(self.ax_time)

        self.radio1 = RadioButtons(ax_radio1, ('Linear','Log'))
        self.radio2 = RadioButtons(ax_radio2, ('Linear','Log'))
        
        ax_radio1.set_title('Left histgram')
        self.radio1.on_clicked(self.ax_ene.change_scale)
        ax_radio2.set_title('Right histgram')
        self.radio2.on_clicked(self.ax_time.change_scale)
        self.ax_ene.set_title(self.TITLE)


    def __readConfig(self,line):
        if(len(line) == 0):
            return
    
        words = line.split('=')
        words[0] = words[0].strip()
        words[1] = words[1].strip()

        if words[0] == 'baseline':
            self.BASE = float(words[1])
        elif words[0] == 'p0':
            self.P[0] = float(words[1])
        elif words[0] == 'p1':
            self.P[1] = float(words[1])
        elif words[0] == 'p2':
            self.P[2] = float(words[1])
        elif words[0] == 'xmin':
            self.xlim[0] = float(words[1])
        elif words[0] == 'xmax':
            self.xlim[1] = float(words[1])
        elif words[0] == 'nbin':
            self.NBIN = int(words[1])
        elif words[0] == 'sampling':
            self.SMP = int(words[1])
        elif words[0] == 'auto_range':
            self.AUTORANGE = self.__getBool(words[1])
        elif words[0] == 'enable':
            self.ENABLE =  self.__getBool(words[1])
        elif words[0] == 'xlabel':
            self.XLABEL = words[1]
        elif words[0] == 'title':
            self.TITLE = words[1]
        elif words[0] == 'RF_channel':
            self.RF = words[1]
        elif words[0] == 'RF_th':
            self.RF_th = int(words[1])
        elif words[0] == 'pulse_th':
            self.PULSE_th = int(words[1])
        elif words[0] == 'time_max':
            self.TIME_MAX = int(words[1])
        elif words[0] == 'display_extra_time':
            self.DISPLAY_EXTRA_TIME = self.__getBool(words[1])
        elif words[0] == 'polar':
            self.POLAR =  self.__getBool(words[1])
        elif words[0] == 'RF_base':
            self.RF_BASE = int(words[1])
        elif words[0] == 'skip_base':
            self.SKIP_BASE = float(words[1])
        elif words[0] == 'calc_base':
            self.CALC_BASE = self.__getBool(words[1])


    def __getBool(self,param):
        if param == 'T':
            return True
        else:
            return False


    def __monitorFile(self):
        currentsize = os.path.getsize(self.rawfile)
        nevent = (currentsize - self.filesize)//(4*self.SMP)
        self.filesize = currentsize
        return nevent

        
    def __calcBase(sefl,singleEvent):
        base_area = 125
        base = np.sum(singleEvent[0:base_area])
        return base/base_area


    def __readEvents(self,n):
        i = 0
        sum = 0.0
        SMP = self.SMP
        P = self.P
        CALC_BASE = self.CALC_BASE
        SKIP_BASE = self.SKIP_BASE
        RF = self.RF
        f_hist = self.f_hist
        format = self.format
        sub_events = [np.empty(0),np.empty(0)]
        BASE = self.BASE
        try:
            while i < n:
                c = f_hist.read(4*SMP)
                if not c:break
                while len(c) != 4*SMP:
                    time.sleep(0.001)
                    c2 = f_hist(4*SMP - len(c))
                    c += c2

                singleEvent = np.array(struct.unpack(format, c))
                
                if CALC_BASE:
                    BASE = self.__calcBase(singleEvent)

                if(SKIP_BASE > 0):
                    base_single = self.__calcBase(singleEvent)
                    if SKIP_BASE >= 1 and base_single > BASE*SKIP_BASE:
                        if RF != '': c=f_rf.read(4*SMP)
                        continue
                    if SKIP_BASE < 0  and base_single < BASE*SKIP_BASE:
                        if RF != '': c=f_rf.read(4*SMP)
                        continue
                
                pulse = np.sum(np.abs(singleEvent-BASE))
                sub_events[0] = np.append(sub_events[0], pulse*pulse*P[2] + pulse*P[1] + P[0])
                
                i += 1
        except struct.error:
            print('chucnk size')
            print(len(c))

        return sub_events


    def __update_events(self):
        while True:
            n = self.__monitorFile()
            n = 10000
            if n == 0:
                time.sleep(0.001)
                axes[0].figure.canvs.draw()
                return

            sub_events = self.__readEvents(n)
            self.q.put(sub_events)
            time.sleep(1)
    
    def update_monitor(self):
        try:
            sub_events = self.q.get_nowait()
            self.events[0] = np.append(self.events[0], sub_events[0])
            self.events[1] = np.append(self.events[1], sub_events[1])
            self.ax_ene.update_hist(sub_events[0])
            self.ax_ene.set_title(self.TITLE + " Events:" + str(self.events[0].size))
            self.ax_ene.figure.canvas.draw()
        except Empty:
            pass

    def terminate(self):
        self.events = None
        self.q.close()
        self.p.terminate()
