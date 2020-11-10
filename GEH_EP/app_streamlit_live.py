import streamlit as st
import pandas as pd
from modules.graph_utilities import (generate_graph_data_handler,
                                     graph_generation)
from modules.sockets_utilities import tcp_server_streamlit
from threading import Thread
import time

# data_delay


# Initializing time window
stop_value = 0


st.sidebar.subheader('Parameters')

time_window = st.sidebar.slider(
    label='Seconds to display:',
    min_value=1,
    max_value=50,
    step=1,
    value=16)

data_freq = st.sidebar.slider(
    label='Graph actualisation frequency (Hz):',
    min_value=1,
    max_value=100,
    step=2,
    value=10)

y_axis = st.sidebar.slider(
    label='y-axis modifier:',
    min_value=-1500,
    max_value=0,
    step=100,
    value=(-1200, -600))

data_freq = 1/data_freq  # Slider is clearer with the period


class data_delay(Thread):

    def __init__(self, data_freq: int = data_freq):
        Thread.__init__(self)
        self.graph_data = pd.DataFrame()
        self.data_freq = data_freq

    def run(self):
        # To DO : make it real time and delete?

        while stop_value == 0:
            try:
                self.graph_data = thr_tcp_server_st.df
                time.sleep(self.data_freq)
            except Exception:
                time.sleep(self.data_freq)


# Loading graph data handler

df_ecg = pd.DataFrame(columns=['ECG'], data=[0])


@st.cache(allow_output_mutation=True, suppress_st_warning=True)
def load_graph_data_handler(df_ecg=df_ecg, time_window=time_window):
    graph_data_handler = generate_graph_data_handler(df_ecg=df_ecg,
                                                     time_window=time_window)
    return graph_data_handler


graph_data_handler = load_graph_data_handler(df_ecg=df_ecg,
                                             time_window=time_window)


# MAIN WINDOW
st.title(body='ECG Visualization')

chart = st.empty()
x, y = graph_data_handler.x_axis, graph_data_handler.y_axis
graph_generation(chart, x, y, y_axis, 1)

# to do: improve warning
st.status = st.sidebar.markdown(
    body='<span style="color: green"> Ready for stream! </span>',
    unsafe_allow_html=True)
print('Ready for stream !')

if st.sidebar.button(label='Start'):

    # Initializing threads
    print('Waiting for HP connexion...')

    thr_tcp_server_st = tcp_server_streamlit()
    thr_data_delay = data_delay(data_freq=data_freq)

    thr_tcp_server_st.start()
    thr_data_delay.start()

    print('Starting stream\n')

    if st.sidebar.button(label='Stop'):
        stop_value = 1
        try:
            thr_tcp_server_st.st_connexion.close()
            print('Connexion closed by stop')
        except Exception:
            pass

    while stop_value == 0:

        x, y = graph_data_handler.update_graph_data_stream(
            df_ecg=thr_data_delay.graph_data)
        graph_generation(chart, x, y, y_axis, 1)
