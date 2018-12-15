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
from multiprocessing import Process, Queue, Value
from queue import Empty
from numba import jit

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
                self.set_xlim((self.xmin,self.xmax))
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
        self.time_lim=[0,self.SMP]
        self.rawfile = rawfile
        self.f_hist = open(rawfile,'rb')
        self.events = [np.empty(0,dtype='f8'),np.empty(0,dtype='f8')]
        self.filesize = Value('i',0)
        self.INTEGRAL_STOP = self.SMP
        self.INTEGRAL_START = 0
        self.TAIL_STOP = self.SMP
        self.TAIL_START = 0
        self.LEFT_HIST = 'energy'
        self.RIGHT_HIST = 'time'
        self.CALC_PSD = False

        try:
            with open(conf) as conf_file:
                for line in conf_file.readlines():
                    self.__readConfig(line)
        except IOError:
            print(conf + " cannot be opend.")

        if self.RF !=  '':
            try:
                rf_file = re.sub('ch[0-9]', 'ch'+ self.RF, self.rawfile)
                self.f_rf = open(rf_file, 'rb')
            except IOError:
                print('RF file:' + rf_file + ' cannot be opened.')
                self.RF = ''

        self.format = ''
        i = 0
        while i < self.SMP:
            self.format += 'i'
            i+= 1
            
        self.__setupAxes(fig, ax_rects)

        self.left = self.__get_column(self.LEFT_HIST)
        self.right = self.__get_column(self.RIGHT_HIST)


    def start(self):
        self.q = Queue()
        self.p = Process(target=self.__update_events)
        self.p.start()


    def __setupAxes(self, fig, ax_rects):
        ax_radio1 = fig.add_axes(ax_rects[0],facecolor='lightgoldenrodyellow') 
        ax_radio2 = fig.add_axes(ax_rects[1],facecolor='lightgoldenrodyellow')

        self.ax_left = self.__getHist(fig,ax_rects[2],self.LEFT_HIST)
        self.ax_right = self.__getHist(fig,ax_rects[3],self.RIGHT_HIST)
        fig.add_axes(self.ax_left)
        fig.add_axes(self.ax_right)

        self.radio1 = RadioButtons(ax_radio1, ('Linear','Log'))
        self.radio2 = RadioButtons(ax_radio2, ('Linear','Log'))
        
        ax_radio1.set_title('Left histgram')
        self.radio1.on_clicked(self.ax_left.change_scale)
        ax_radio2.set_title('Right histgram')
        self.radio2.on_clicked(self.ax_right.change_scale)
        self.ax_left.set_title(self.TITLE)
        self.ax_left.set_xlabel(self.XLABEL, labelpad = 0.01)

        self.ax_right.set_title(self.RIGHT_HIST)


    def __get_column(self,kind):
        if kind == 'energy':
            return 0
        elif kind == 'time':
            return 1
        elif kind == 'psd':
            return 2
        else:
            return -1


    def __getHist(self, fig,rect ,kind):
        if kind == 'energy':
            return Realtime_histogram(fig,rect,self.NBIN,self.xlim[0],self.xlim[1],self.AUTORANGE)
        elif kind == 'time':
            return Realtime_histogram(fig,rect,self.SMP,0,self.SMP,False)
        elif kind == 'psd':
            return Realtime_histogram(fig,rect,self.NBIN,0,1,False)
        else:
            print('Invalid kind of histogram : ',kind)
            return Realtime_histogram(fig,rect,1,0,1,False)


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
            self.time_lim[1] = int(words[1])
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
        elif words[0] == 'time_max':
            self.time_lim[1] = int(words[1])
        elif words[0] == 'time_min':
            self.time_lim[0] = int(words[1])
        elif words[0] == 'integral_start':
            self.INTEGRAL_START = int(words[1])
        elif words[0] == 'integral_stop':
            self.INTEGRAL_STOP = int(words[1])
        elif words[0] == 'tail_start':
            self.TAIL_START = int(words[1])
        elif words[0] == 'tail_stop':
            self.TAIL_STOP = int(words[1])
        elif words[0] == 'calc_psd':
            self.CALC_PSD = self.__getBool(words[1])
        elif words[0] == 'left_hist':
            self.LEFT_HIST = words[1]
        elif words[0] == 'right_hist':
            self.RIGHT_HIST = words[1]


    def __getBool(self,param):
        if param == 'T':
            return True
        else:
            return False


    def __monitorFile(self):
        currentsize = os.path.getsize(self.rawfile)
        nevent = (currentsize - self.filesize.value)//(4*self.SMP)
        self.filesize.value = currentsize
        return nevent


    @jit
    def __calcBase(sefl,singleEvent):
        base_area = 125
        base = np.sum(singleEvent[0:base_area])
        return base/base_area

        
    @jit
    def __calcTimeDiff(self, base, det_event, rf_event):
        rise_up = -1
        pulse_th = self.PULSE_th
        rf_th = self.RF_th
        polar = self.POLAR
        rf_base = self.RF_BASE

        for value in det_event:
            rise_up += 1
            if polar:
                if value - base >=  pulse_th:
                    break
            else:
                if base - value >=  pulse_th:
                    break

        i = rise_up
        if rf_base - rf_event[i] > rf_th:
            for value in rf_event[rise_up+1:]:
                i += 1
                if rf_base - value <= rf_th:
                    return i - 1
        else:
            for value in rf_event[rise_up-1::-1]:
                i -= 1
                if rf_base - value > rf_th:
                    return i

        return 0


    @jit('f8[:,:,:](pyobject,i8)')
    def __readEvents(self,n):
        i = 0
        SMP = self.SMP
        P = self.P
        CALC_BASE = self.CALC_BASE
        SKIP_BASE = self.SKIP_BASE
        RF = self.RF
        f_rf = None
        f_hist = self.f_hist
        if RF != '':
            f_rf = self.f_rf
        format = self.format
        sub_events = [np.empty(0),np.empty(0),np.empty(0)]
        BASE = self.BASE
        time_lim = self.time_lim
        INTEGRAL_STOP = self.INTEGRAL_STOP
        INTEGRAL_START = self.INTEGRAL_START
        TAIL_STOP = self.TAIL_STOP
        TAIL_START = self.TAIL_START
        CALC_PSD = self.CALC_PSD

        while i < n:
            i += 1
            c = f_hist.read(4*SMP)
            if not c:break
            while len(c) != 4*SMP:
                print( self.TITLE + ' is reading events... now ', len(c), '/', 4*SMP,' bytes. subevent number is ', i)
                time.sleep(0.5)
                c2 = f_hist.read(4*SMP - len(c))
                c += c2
                
            singleEvent = np.array(struct.unpack(format, c))
            
            if CALC_BASE:
                BASE = self.__calcBase(singleEvent)

            if(SKIP_BASE > 0):
                base_single = self.__calcBase(singleEvent)
                if SKIP_BASE >= 1 and base_single > BASE*SKIP_BASE:
                    if RF != '':
                        c=f_rf.read(4*SMP)
                        while len(c) != 4*SMP:
                            print( self.TITLE + 'is reading RF signals... now ', len(c), '/', 4*SMP,' bytes. subevent number is ', i)
                            time.sleep(0.5)
                            c2 = f_rf.read(4*SMP - len(c))
                            c += c2

                    continue
                if SKIP_BASE < 0  and base_single < BASE*SKIP_BASE:
                    if RF != '': 
                        c=f_rf.read(4*SMP)
                        while len(c) != 4*SMP:
                            print( self.TITLE + 'is reading RF signals... now ', len(c), '/', 4*SMP,' bytes. subevent number is ', i)
                            time.sleep(0.5)
                            c2 = f_rf.read(4*SMP - len(c))
                            c += c2

                    continue
                    
            if RF != '':
                c = f_rf.read(4*SMP)
                if not c:continue
                while len(c) != 4*SMP:
                    print( self.TITLE + 'is reading RF signals... now ', len(c), '/', 4*SMP,' bytes. subevent number is ', i)
                    time.sleep(0.5)
                    c2 = f_rf.read(4*SMP - len(c))
                    c += c2
                
                rf_singleEvent = struct.unpack(format, c)
                timediff = self.__calcTimeDiff(BASE, singleEvent, rf_singleEvent)

                if timediff < time_lim[0] or timediff > time_lim[1]:
                    continue

                sub_events[1] = np.append(sub_events[1], timediff)

            pulse = np.sum(np.abs(singleEvent[INTEGRAL_START:INTEGRAL_STOP]-BASE))
            sub_events[0] = np.append(sub_events[0], pulse*pulse*P[2] + pulse*P[1] + P[0])
            
            if CALC_PSD:
                tail = np.sum(np.abs(singleEvent[TAIL_START:TAIL_STOP]-BASE))
                ratio = tail/pulse
                sub_events[2] = np.append(sub_events[2],ratio)

#        except struct.error:
#            print('chucnk size')
#            print(len(c))
        return sub_events


    def __update_events(self):
        while True:
            n = self.__monitorFile()
            if n == 0:
                time.sleep(0.01)
                continue

            sub_events = self.__readEvents(n)
            self.q.put(sub_events)
            time.sleep(1)
    

    def update_monitor(self):
        if self.left < 0 or self.right < 0:
            return

        try:
            sub_events = self.q.get_nowait()
            self.events[0] = np.append(self.events[0], sub_events[self.left])
            self.events[1] = np.append(self.events[1], sub_events[self.right])
            self.ax_left.update_hist(sub_events[self.left])
            self.ax_right.update_hist(sub_events[self.right])
            self.ax_left.set_title(self.TITLE + " Events:" + str(self.events[0].size))
            self.ax_left.figure.canvas.draw()
        except Empty:
            pass


    def terminate(self):
        self.events = None
        self.q.close()
        self.p.terminate()
