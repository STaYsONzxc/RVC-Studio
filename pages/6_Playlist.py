import os
import sys
import numpy as np
import pandas as pd
import streamlit as st

from webui import DEVICE_OPTIONS, MENU_ITEMS, i18n, config
from webui.downloader import SONG_DIR
st.set_page_config(layout="centered",menu_items=MENU_ITEMS)

from webui.components import active_subprocess_list, file_uploader_form, initial_vocal_separation_params, initial_voice_conversion_params, vocal_separation_form, voice_conversion_form
from webui.utils import gc_collect, get_filenames, get_index, get_optimal_torch_device


from webui.player import PlaylistPlayer
from types import SimpleNamespace
from webui.contexts import SessionStateContext
from webui.audio import SUPPORTED_AUDIO

CWD = os.getcwd()
if CWD not in sys.path:
    sys.path.append(CWD)

def get_models(folder="."):
    fnames = get_filenames(root="./models",folder=folder,exts=["pth","pt"])
    return fnames

def init_inference_state():
    state = SimpleNamespace(
        player=None,
        playlist = get_filenames(exts=SUPPORTED_AUDIO,name_filters=[""],folder="songs"),
        models=get_models(folder="RVC"),
        model_name=None,
        
        split_vocal_config=initial_vocal_separation_params(),
        vocal_change_config=initial_voice_conversion_params(),
        shuffle=False,
        loop=False,
        volume=1.0,
        device=get_optimal_torch_device()
    )
    return vars(state)

def refresh_data(state):
    state.split_vocal_config.uvr5_models = get_filenames(root="./models",name_filters=["vocal","instrument"])
    state.split_vocal_config.uvr5_preprocess_models = get_filenames(root="./models",name_filters=["echo","reverb","noise"])
    state.models = get_models(folder="RVC")
    state.playlist = get_filenames(exts=SUPPORTED_AUDIO,name_filters=[""],folder="songs")
    gc_collect()
    return state
    
def render_vocal_separation_form(state):
    with st.form("inference.split_vocals.expander"):
        split_vocal_config = vocal_separation_form(state.split_vocal_config)
        
        if st.form_submit_button(i18n("inference.save.button"),type="primary"):
            state.split_vocal_config = split_vocal_config
            update_player_args(split_audio_params=vars(state.split_vocal_config))
    return state

def render_vocal_conversion_form(state):
    with st.form("inference.convert_vocals.expander"):
        vocal_change_config = voice_conversion_form(state.vocal_change_config)
        
        if st.form_submit_button(i18n("inference.save.button"),type="primary"):
            state.vocal_change_config = vocal_change_config
            update_player_args(vc_single_params=vars(state.vocal_change_config))
    return state

def set_volume(state):
    if state.player and state.volume!=state.player.volume: state.player.set_volume(state.volume)
def set_loop(state):
    if state.player and state.loop!=state.player.loop: state.player.set_loop(state.loop)
def set_shuffle(state):
    if state.player:
        if state.shuffle:
            if not state.player.shuffled: state.player.shuffle()
        else:
            state.player.playlist = state.playlist
            state.player.shuffled = False
def update_player_args(**args):
    if state.player: state.player.set_args(**args)

if __name__=="__main__":
    with SessionStateContext("playlist",initial_state=init_inference_state()) as state:

        file_uploader_form(
                SONG_DIR,"Upload your songs",
                types=SUPPORTED_AUDIO+["zip"],
                accept_multiple_files=True)

        col1, col2 = st.columns(2)
        state.model_name = st.selectbox(
            i18n("inference.voice.selectbox"),
            options=state.models,
            index=get_index(state.models,state.model_name),
            format_func=lambda option: os.path.basename(option).split(".")[0],
            disabled=state.player is not None
            )
        
        with st.form("song.settings.form"):
            state.volume = st.select_slider("Volume",options=np.linspace(0.,1.,21),value=state.volume,
                                            format_func=lambda x:f"{x*100:3.0f}%")
            col1, col2, col3 = st.columns(3)
            state.loop = col1.checkbox("Loop",value=state.loop)
            state.shuffle = col2.checkbox("Shuffle",value=state.shuffle)
            state.device = col3.radio(
                i18n("inference.device"),
                disabled=not config.has_gpu,
                options=DEVICE_OPTIONS,horizontal=True,
                index=get_index(DEVICE_OPTIONS,state.device))
            
            if st.form_submit_button("Update"):
                set_volume(state)
                set_loop(state)
                set_shuffle(state)

        col1, col2, col3, col4 = st.columns(4)

        if col1.button(i18n("inference.refresh_data.button"),use_container_width=True):
            state = refresh_data(state)
            st.experimental_rerun()

        if col2.button("Play" if state.player is None else ("Resume" if state.player.paused else "Pause"), type="primary",use_container_width=True,
                    disabled=not (state.split_vocal_config.model_paths and state.model_name)):
            if state.player is None:
                state.player = PlaylistPlayer(state.playlist,
                                              shuffle=state.shuffle,
                                              loop=state.loop,
                                              volume=state.volume,
                                                model_name=state.model_name,
                                                config=config,
                                                device=state.device,
                                                split_audio_params=vars(state.split_vocal_config),
                                                vc_single_params=vars(state.vocal_change_config))
            else:
                if state.player.paused:
                    state.player.resume()
                else:
                    state.player.pause()
            st.experimental_rerun()

        if col3.button("Next", use_container_width=True,disabled = state.player is None):
            state.player.skip()
            st.experimental_rerun()
        if col4.button("Stop",type="primary",use_container_width=True,disabled = state.player is None):
            if state.player is not None: state.player.stop()
            del state.player
            state.player = None
            gc_collect()
            st.experimental_rerun()
            
        with st.expander("Settings", expanded=not (state.player and len(state.split_vocal_config.model_paths))):
            vs_tab, vc_tab = st.tabs(["Split Vocal", "Vocal Change"])

            with vs_tab:
                state = render_vocal_separation_form(state)

            with vc_tab:
                state = render_vocal_conversion_form(state)

        active_subprocess_list()

        if state.player:
            st.write(state.player)
            df = pd.DataFrame(state.player.playlist,columns=["Songs"])
            index = np.arange(len(df))
            df.index=np.where([False if state.player.current_song is None else
                               state.player.current_song in song
                               for song in state.player.playlist],"⭐",index)
            st.table(df)