'''
Script to create the session folder structure
'''
#%%
import os
import re
import shutil
import warnings
from datetime import datetime, timedelta
from glob import glob
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

from trialexp.process.pycontrol.data_import import session_dataframe
from trialexp.process.pyphotometry.utils import import_ppd
from trialexp.utils.rsync import Rsync_aligner, RsyncError

#%% 
export_base_path = Path('Z:\Teris\ASAP\expt_sessions')
pycontrol_folder = Path('Z:\\Teris\\ASAP\\pycontrol\\reaching_go_spout_bar_nov22')
pyphoto_folder = Path('Z:\\Teris\\ASAP\\pyphotometry\\reaching_go_spout_bar_nov22')

pycontrol_files = list(pycontrol_folder.glob('*.txt'))
pyphoto_files = list(pyphoto_folder.glob('*.ppd'))


#%% Build a dataframe of the photometry files for matching later
def parse_pyhoto_fn(fn):
    pattern = r'(\w+)-(.*)\.ppd'
    m = re.search(pattern, fn.name)
    if m:
        animal_id = m.group(1)
        date_string = m.group(2)
        expt_datetime = datetime.strptime(date_string, "%Y-%m-%d-%H%M%S")
        
        return {'animal_id':animal_id, 'path':fn, 
                'filename':fn.stem, 
                'timestamp':expt_datetime}

df_pyphoto = pd.DataFrame(list(map(parse_pyhoto_fn, pyphoto_files)))

#%%
def parse_pycontrol_fn(fn):
    pattern = r'(\w+)-(.*)\.txt'
    m = re.search(pattern, fn.name)
    if m:
        animal_id = m.group(1)
        date_string = m.group(2)
        expt_datetime = datetime.strptime(date_string, "%Y-%m-%d-%H%M%S")
        
        return {'animal_id':animal_id, 'path':fn,                 
                'session_id':fn.stem,
                'filename':fn.stem, 
                'timestamp':expt_datetime}
    
df_pycontrol = pd.DataFrame(list(map(parse_pycontrol_fn, pycontrol_files)))

#%% Match
#Try to match pycontrol file together with pyphotometry file

matched_path = []
matched_fn  =[]

for _, row in df_pycontrol.iterrows():
    min_td = np.min(abs(row.timestamp - df_pyphoto.timestamp))
    idx = np.argmin(abs(row.timestamp - df_pyphoto.timestamp))

    if min_td< timedelta(minutes=5):
        matched_path.append(df_pyphoto.iloc[idx].path)
        matched_fn.append(df_pyphoto.iloc[idx].filename)
    else:
        matched_path.append(None)
        matched_fn.append(None)

df_pycontrol['pyphoto_path'] = matched_path
df_pycontrol['pyphoto_filename'] = matched_fn
df_pycontrol = df_pycontrol[df_pycontrol.animal_id!='00'] # do not copy the test data
df_pycontrol = df_pycontrol.dropna(subset='pyphoto_path')

# %%
def create_sync(pycontrol_file, pyphotometry_file):
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        pyphotometry_file = import_ppd(pyphotometry_file)
        data_pycontrol = session_dataframe(pycontrol_file)

        photo_rsync = pyphotometry_file['pulse_times_2']
        pycontrol_rsync = data_pycontrol[data_pycontrol.name=='rsync'].time
        
        try:
            return Rsync_aligner(pulse_times_A= photo_rsync, 
            pulse_times_B= pycontrol_rsync, plot=False) #align pycontrol time to pyphotometry time
        except (RsyncError, ValueError):
            return None

# %%
matched = []
for _, row in df_pycontrol.iterrows():
    session_id = row.session_id
    animal_id = row.animal_id
    
    target_pycontrol_folder = Path(export_base_path, session_id, 'pycontrol')
    target_pyphoto_folder = Path(export_base_path, session_id, 'pyphotometry')
    
    if not target_pycontrol_folder.exists():
        # create the base folder
        target_pycontrol_folder.mkdir(parents=True)
        target_pyphoto_folder.mkdir(parents=True)
        
        pycontrol_file = row.path
        pyphotometry_file = row.pyphoto_path
        
        #copy the pycontrol files
        shutil.copy(pycontrol_file, target_pycontrol_folder)
        
        #copy all the analog data
        analog_files = pycontrol_file.parent.glob(f'{session_id}*.pca')
        for f in analog_files:
            shutil.copy(f, target_pycontrol_folder) 
        
        #Copy pyphotometry file is they match
        if create_sync(str(pycontrol_file), str(pyphotometry_file)) is not None:
            matched.append(True)
            shutil.copy(pyphotometry_file, target_pyphoto_folder)
        else:
            matched.append(False)

    else:
        print(f'{session_id} already exist')
df_pycontrol['matched'] = matched
# %%
