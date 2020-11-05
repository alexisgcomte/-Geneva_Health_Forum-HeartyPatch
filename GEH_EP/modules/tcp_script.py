# coding: utf-8
#
#  HeartyPatch Client
#
# Copyright Douglas Williams, 2018
#
# Licensed under terms of MIT License (http://opensource.org/licenses/MIT).
#

# In Python3

import socket
from pprint import pprint
import os
import sys
import signal as sys_signal
import struct

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import scipy.signal as signal
import time
import datetime

from modules.graph_utilities import (generate_graph_data_handler,
                                     graph_generation)
import streamlit as st

hp_host = '192.168.0.106'
hp_port = 4567





class HeartyPatch_TCP_Parser:


    # Create a class to store TCP protocol info and received info
    # 'add_data' add received bytes to data
    # 'process_packets' checks for integrity and output the info

    # Packet Validation
    CESState_Init = 0
    CESState_SOF1_Found = 1
    CESState_SOF2_Found = 2
    CESState_PktLen_Found = 3

    # CES CMD IF Packet Format
    CES_CMDIF_PKT_START_1 = 0x0A
    CES_CMDIF_PKT_START_2 = 0xFA
    CES_CMDIF_PKT_STOP = 0x0B

    # CES CMD IF Packet Indices
    CES_CMDIF_IND_LEN = 2
    CES_CMDIF_IND_LEN_MSB = 3
    CES_CMDIF_IND_PKTTYPE = 4
    CES_CMDIF_PKT_OVERHEAD = 5
    CES_CMDIF_PKT_DATA = CES_CMDIF_PKT_OVERHEAD


    ces_pkt_seq_bytes   = 4  # Buffer for Sequence ID
    ces_pkt_ts_bytes   = 8  # Buffer for Timestamp
    ces_pkt_rtor_bytes = 4  # R-R Interval Buffer
    ces_pkt_ecg_bytes  = 4  # Field(s) to hold ECG data

    # Used to be 3
    Expected_Type = 3

    min_packet_size = 19

    def __init__(self):
        self.state = self.CESState_Init
        self.data = bytes()
        self.packet_count = 0
        self.bad_packet_count = 0
        self.bytes_skipped = 0
        self.total_bytes = 0
        self.all_seq = []
        self.all_ts = []
        self.all_rtor = []
        self.all_hr = []
        self.all_ecg = []
        self.df = pd.DataFrame(columns =['ECG'])

        pass

    def add_data(self, new_data):
        self.data += new_data
        self.total_bytes += len(new_data)

    def process_packets(self):
        while len(self.data) >= self.min_packet_size:
            if self.state == self.CESState_Init:
                if self.data[0] == self.CES_CMDIF_PKT_START_1:
                    self.state = self.CESState_SOF1_Found
                else:
                    self.data = self.data[1:]    # skip to next byte
                    self.bytes_skipped += 1
                    continue
            elif self.state == self.CESState_SOF1_Found:
                if self.data[1] == self.CES_CMDIF_PKT_START_2:
                    self.state = self.CESState_SOF2_Found
                else:
                    self.state = self.CESState_Init
                    self.data = self.data[1:]    # start from beginning
                    self.bytes_skipped += 1
                    continue
            elif self.state == self.CESState_SOF2_Found:
                # sanity check header for expected values

                pkt_len = (256 * (self.data[self.CES_CMDIF_IND_LEN_MSB])) + (
                    self.data[self.CES_CMDIF_IND_LEN])

                # Make sure we have a full packet
                if len(self.data) < (self.CES_CMDIF_PKT_OVERHEAD +
                                     pkt_len + 2):
                    print('break')
                    break

                if (self.data[self.CES_CMDIF_IND_PKTTYPE]  != self.Expected_Type
                    or self.data[self.CES_CMDIF_PKT_OVERHEAD+pkt_len+1] != self.CES_CMDIF_PKT_STOP):

                    print('unexpected_type')
                    #if True:
                    #      print('pkt_len', pkt_len)
                    #      print(self.data[self.CES_CMDIF_IND_PKTTYPE], self.Expected_Type)
                    #      print(self.data[self.CES_CMDIF_IND_PKTTYPE] != self.Expected_Type)
                    #
                    #      for j in range(0, self.CES_CMDIF_PKT_OVERHEAD):
                    #          print format(ord(self.data[j]),'02x'),
                    #      print

                    #        for j in range(self.CES_CMDIF_PKT_OVERHEAD, self.CES_CMDIF_PKT_OVERHEAD+pkt_len):
                    #            print format(ord(self.data[j]),'02x'),
                    #        print

                    #        for j in range(self.CES_CMDIF_PKT_OVERHEAD+pkt_len, self.CES_CMDIF_PKT_OVERHEAD+pkt_len+2):
                    #            print format(ord(self.data[j]),'02x'),
                    #        print
                    #        print self.CES_CMDIF_PKT_STOP,
                    #        print ord(self.data[self.CES_CMDIF_PKT_OVERHEAD+pkt_len+2]) != self.CES_CMDIF_PKT_STOP
                    #        print
                    #    pass
                    # unexpected packet format
                    self.state = self.CESState_Init
                    self.data = self.data[1:]    # start from beginning
                    self.bytes_skipped += 1
                    self.bad_packet_count += 1
                    continue

                        # Parse Payload
                payload = self.data[self.CES_CMDIF_PKT_OVERHEAD:self.CES_CMDIF_PKT_OVERHEAD+pkt_len+1]

                ptr = 0
                # Process Sequence ID
                seq_id = struct.unpack('<I', payload[ptr:ptr+4])[0]
                self.all_seq.append(seq_id)
                ptr += self.ces_pkt_seq_bytes

                # Process Timestamp
                ts_s = struct.unpack('<I', payload[ptr:ptr+4])[0]
                ts_us = struct.unpack('<I', payload[ptr+4:ptr+8])[0]
                timestamp = ts_s + ts_us/1000000.0
                self.all_ts.append(timestamp)
                ptr += self.ces_pkt_ts_bytes

                # Process R-R Interval
                rtor = struct.unpack('<I', payload[ptr:ptr+4])[0]
                self.all_rtor.append(rtor)
                if rtor == 0:
                    self.all_hr.append(0)
                else:
                    self.all_hr.append(60000.0/rtor)

                ptr += self.ces_pkt_rtor_bytes

                assert ptr == 16
                assert pkt_len == (16 + 8 * 4)

                # Process Sequence ID
                while ptr < pkt_len:
                    ecg = struct.unpack('<i', payload[ptr:ptr+4])[0] / 1000.0
                    self.all_ecg.append(ecg)
                    self.df = self.df.append({'ECG': ecg}, ignore_index=True)
                    #sys.stdout.write(str(ecg)+str('\n'))
                    #sys.stdout.flush()
                    ptr += self.ces_pkt_ecg_bytes

                self.packet_count += 1
                self.state = self.CESState_Init
                # start from beginning
                self.data = self.data[self.CES_CMDIF_PKT_OVERHEAD+pkt_len+2:]

                #sys.stdout.write('\n Packet Processed')
                #sys.stdout.flush()


soc = None
hp = None
tStart = None

class connect_hearty_patch:

    global connect_hearty_patch

    def __init__(self, hp_host='heartypatch.local', hp_port=4567):

        print('attempting connexion')

        self.hp_host = hp_host
        self.hp_port = hp_port
        self.sock = socket.create_connection((self.hp_host, self.hp_port))


        # Try connecting, if not close the conection and restart

        try:
            print('attempt_1')
            self.sock = socket.create_connection((self.hp_host, self.hp_port))
            print('socket created')
        except Exception:
            print('attempt_2')
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = socket.create_connection((self.hp_host, self.hp_port))
            print('socket created after attempt')

        print(self.sock)




def get_heartypatch_data(
    max_packets=10000,
    hp_host='heartypatch.local',
    max_seconds=5):

    print('\n Starting data Streamin')

    global soc
    global hp


    tcp_reads = 0
    hp = HeartyPatch_TCP_Parser()
    print('\n Starting data Streamin')

# Try connecting, if not close the conection and restart

    try:
        soc = socket.create_connection((hp_host, hp_port))
    except Exception:
        try:
            soc.close()
        except Exception:
            pass
        soc = socket.create_connection((hp_host, hp_port))

    sys.stdout.write('Connexion successful \n')
    sys.stdout.flush()

    print('\n Starting data Streamin')

    i = 0
    pkt_last = 0
    print(soc)
    txt = soc.recv(16*1024)  # discard any initial results

    tStart = time.time()
    while max_packets == -1 or hp.packet_count < max_packets:
        txt = soc.recv(16*1024)
        hp.add_data(txt)
        hp.process_packets()

        ### DATA HANDLING

        sys.stdout.flush()

        #sys.stdout.write('\n graph handler ok')
        #sys.stdout.flush()

        #graph_generation(chart, x, y, slider_y_axis, data_freq)
        

        ###
        i += 1

    # useful?

        tcp_reads += 1
        if tcp_reads % 50 == 0:
            sys.stdout.write(".")
            sys.stdout.flush()

        if hp.packet_count - pkt_last >= 1000:
            pkt_last = pkt_last + 1000
            sys.stdout.write(hp.packet_count//1000)
            sys.stdout.flush()

        if time.time() - tStart > max_seconds:
            break

    return hp.df

def finish():

    # After the the stream, export data

    sys.stdout.write('\nStarting finishing pipeline \n ')
    sys.stdout.flush()

    global soc
    global hp
    global tStart
    global fname

    if soc is not None:
        soc.close()

    # Saving global log

    #sys.stdout.write('Exporting global log \n ')
    #sys.stdout.flush()

    #header = 'seq, timestamp, rtor, hr'
    #np.savetxt('data/results/log_{}.csv'.format(str(datetime.datetime.today())),
    #           zip(hp.all_seq, hp.all_ts, hp.all_rtor, hp.all_hr),
    #           fmt=('%d', '%.3f', '%d', '%d'),
    #           header=header, delimiter=',')

    # Saving raw data

    # text_file = open("data/results/output_{}.txt".format(str(datetime.datetime.today())), "w")
    # n = text_file.write(str(hp.data))
    # text_file.close()


    sys.stdout.write('Exporting ECG dataset\n ')
    sys.stdout.flush()

    # Saving ECG data in DataFrame format
    hp.df.to_csv('data/results/df_{}.csv'.format(str(datetime.datetime.today())), index=False)

    sys.stdout.write('All exported!\n')
    sys.stdout.flush()


df_ecg = pd.DataFrame(columns=['ECG'], data=[0])
time_window = 5

def start_stream(graph_data_handler=generate_graph_data_handler(df_ecg, time_window)):

    print('Starting stream')
    st.sidebar.write('Starting stream')
    hp_host = 'heartypatch.local'
    hp = None
    tStart = None
    socket = None

#    soc = socket

    max_packets= 10000
    max_seconds = 1 # default recording duration is 10min


   # print('get_heartypatch_data stream')

 
    #connexion = connect_hearty_patch(hp_host=hp_host, hp_port=hp_port)
    temp_df = get_heartypatch_data(max_packets=max_packets,
                                   max_seconds=max_seconds,
                                   hp_host=hp_host)

    print('graph update')
    sys.stdout.flush()

    #x, y  = graph_data_handler.update_graph_data(temp_df, time_window)

    #print(y)
    #graph_generation(chart, x, y, slider_y_axis, data_freq)

    if soc is not None:
        soc.close()

    if soc is not None:
        soc.close()
    


    finish()
    print('\n Properly Run! \n\n')

    return temp_df



# if __name__== "__main__":
#
#    max_packets= 10000
#    max_seconds = 5 # default recording duration is 10min
#    hp_host = 'heartypatch.local'
#
#    get_heartypatch_data(max_packets=max_packets, max_seconds=max_seconds, hp_host=hp_host)
#    finish()

