#!/usr/bin/env python
# coding: utf-8

# In[8]:


#get_ipython().run_line_magic('matplotlib', 'inline')
#get_ipython().run_line_magic('load_ext', 'autoreload')
#get_ipython().run_line_magic('autoreload', '2')
# Cell magic method always stays at the top of the cell

# Imports from the Python standard library should be at the top
import os
import copy
import pickle
import itertools 

# Do not import * unless you know what you are doing
import numpy as np 
import pandas as pd

import fsps
import sedpy
import lineid_plot

from sedpy.observate import getSED, vac2air, air2vac

import matplotlib.pyplot as plt
from matplotlib import rc
plt.rc('text', usetex=True)

import astropy.units as u
from astropy.io import ascii
from astropy.table import Table, Column
from astropy.constants import c, L_sun, pc
from astropy.cosmology import FlatLambdaCDM
from astropy.io import fits

from specutils import Spectrum1D
from specutils import SpectralRegion
from specutils.fitting import fit_generic_continuum
from specutils.analysis import equivalent_width

from prospect import models
from prospect.models import priors

from scipy.stats import entropy

import torch
import torch.nn as nn

# re-defining plotting defaults
from matplotlib import rcParams

from dwarf_models import SDSS_EMLINES, simulate_dwarf_sed, test_single_model,    sigma_clipping_continuum, measure_ew_emission_line, design_model_grid,    generate_dwarf_population, measure_color_ew, plot_models_with_sdss, setup_fsps_spop

rcParams.update({'xtick.major.pad': '7.0'})
rcParams.update({'xtick.major.size': '7.5'})
rcParams.update({'xtick.major.width': '1.5'})
rcParams.update({'xtick.minor.pad': '7.0'})
rcParams.update({'xtick.minor.size': '3.5'})
rcParams.update({'xtick.minor.width': '1.0'})
rcParams.update({'ytick.major.pad': '7.0'})
rcParams.update({'ytick.major.size': '7.5'})
rcParams.update({'ytick.major.width': '1.5'})
rcParams.update({'ytick.minor.pad': '7.0'})
rcParams.update({'ytick.minor.size': '3.5'})
rcParams.update({'ytick.minor.width': '1.0'})
rcParams.update({'axes.titlepad': '15.0'})
rcParams.update({'font.size': 22})


# ### Read in the SDSS catalog

# In[2]:

def data_to_distribution(data, bin_size):
    
    data_hist = np.histogram(data, bins = bin_size)[0]

    data_hist_norm = np.array([float(i+1e-4)/sum(data_hist) for i in data_hist])

    return data_hist_norm

def entropy(obs, model):
    
    x = torch.tensor([obs])
    y = torch.tensor([model])
    
    criterion = nn.KLDivLoss()
    loss = criterion(x.log(),y)   
    
    return loss.item()


sdss_cat = Table.read('/Users/runquanguan/Documents/Dwarf_SDSS_8_9_SF_v2.0.fits')

em_flag = (np.isfinite(sdss_cat['M_u']) & np.isfinite(sdss_cat['M_r']) &            np.isfinite(sdss_cat['M_g']) & np.isfinite(sdss_cat['M_i']) &           np.isfinite(sdss_cat['OIII_5007_EQW']) &            np.isfinite(sdss_cat['H_ALPHA_EQW']) &           np.isfinite(sdss_cat['H_BETA_EQW']))

sdss_use = sdss_cat[em_flag]


SDSS_EMLINES = {    'OII_3726': {'cen':3726.032, 'low':3717.0, 'upp':3737.0},    'OII_3729': {'cen':3728.815, 'low':3717.0, 'upp':3737.0},    'NeIII_3869': {'cen':3869.060, 'low':3859.0, 'upp':3879.0},     'H_delta': {'cen':4101.734, 'low':4092.0, 'upp':4111.0},    'H_gamma': {'cen':4340.464, 'low':4330.0, 'upp':4350.0},    'OIII_4363': {'cen':4363.210, 'low':4350.0, 'upp':4378.0},    'H_beta': {'cen':4861.325, 'low':4851.0, 'upp':4871.0},    'OIII_4959': {'cen':4958.911, 'low':4949.0, 'upp':4969.0},    'OIII_5007': {'cen':5006.843, 'low':4997.0, 'upp':5017.0},    'HeI_5876': {'cen':5875.67, 'low':5866.0, 'upp':5886.0},    'OI_6300': {'cen':6300.304, 'low':6290.0, 'upp':6310.0},    'NII_6548': {'cen':6548.040, 'low':6533.0, 'upp':6553.0},    'H_alpha': {'cen':6562.800, 'low':6553.0, 'upp':6573.0},    'NII_6584': {'cen':6583.460, 'low':6573.0, 'upp':6593.0},    'SII_6717': {'cen':6716.440, 'low':6704.0, 'upp':6724.0},    'SII_6731': {'cen':6730.810, 'low':6724.0, 'upp':6744.0},    'ArIII7135': {'cen':7135.8, 'low':7130.0, 'upp':7140.0}
}


# In[3]:


from hyperopt import hp, fmin, rand, tpe, space_eval

space = [hp.normal('tau_mean', 2.6, 0.3),
         hp.normal('const_mean', 0.3, 0.1),
         hp.normal('tage_mean', 6.5, 2.0),
         hp.normal('fburst_mean', 0.6, 0.1),
         hp.normal('tburst_mean', 5.0, 0.5),
         hp.normal('logzsol_mean', 0.8, 0.5),
         hp.normal('gas_logz_mean', 0.5, 0.5),
         hp.normal('gas_logu_mean', 3.2, 0.5),

         hp.normal('tau_sig', 0.7, 0.2),
         hp.normal('const_sig', 0.5, 0.1),
         hp.normal('tage_sig', 2.0, 0.5),
         hp.normal('fburst_sig', 0.1, 0.1),
         hp.normal('tburst_sig', 0.5, 0.1),
         hp.normal('logzsol_sig', 0.7, 0.2),
         hp.normal('gas_logz_sig', 0.7, 0.2),
         hp.normal('gas_logu_sig', 0.5, 0.1), 
        ]


# In[4]:

# compute KL divergence between two distributions
def loss(true_set, predict_set, bins_range):
    
    sdss_hist = np.histogram(true_set, bins = bins_range)[0]
    sps_hist = np.histogram(predict_set, bins = bins_range)[0]
    
    # get rid of divided by zero problem
    sdss_hist_norm = [float(i+1e-4)/sum(sdss_hist) for i in sdss_hist]
    sps_hist_norm = [float(i+1e-4)/sum(sps_hist) for i in sps_hist]
    
    x = torch.tensor([sdss_hist_norm])
    y = torch.tensor([sps_hist_norm])
    
    criterion = nn.KLDivLoss()
    loss = criterion(x.log(),y)   
    
    return loss.item()

    
    


# In[ ]:


def loss_function(args):

    
    tau_mean, const_mean, tage_mean, fburst_mean, tburst_mean, logzsol_mean, gas_logz_mean, gas_logu_mean,\
        tau_sig, const_sig, tage_sig, fburst_sig, tburst_sig, logzsol_sig, gas_logz_sig, gas_logu_sig = args
    
    set_size = 3000

    tau_arr = [float(priors.ClippedNormal(mean = abs(tau_mean), sigma=abs(tau_sig), 
                                          mini=1.0, maxi=8.0).sample()) for _ in range(set_size)]
    
    const_arr =  [float(priors.ClippedNormal(mean = abs(const_mean), sigma=abs(const_sig), 
                                             mini=0.0, maxi=0.5).sample()) for _ in range(set_size)]
    
    tage_arr =  [float(priors.ClippedNormal(mean = abs(tage_mean), sigma=abs(tage_sig), 
                                            mini=1.0, maxi=11.0).sample()) for _ in range(set_size)]
    
    fburst_arr =  [float(priors.ClippedNormal(mean = abs(fburst_mean), sigma=abs(fburst_sig), 
                                              mini=0.0, maxi=0.8).sample()) for _ in range(set_size)]
    
    tburst_arr =  [float(priors.ClippedNormal(mean = abs(tburst_mean), sigma=abs(tburst_sig), 
                                              mini=0.0, maxi=abs(tage_mean) ).sample()) for _ in range(set_size)]
    
    logzsol_arr =  [float(priors.ClippedNormal(mean = -1 * abs(logzsol_mean), sigma=abs(logzsol_sig), 
                                               mini=-1.5, maxi=0.0).sample()) for _ in range(set_size)]
    
    gas_logz_arr =  [float(priors.ClippedNormal(mean = -1 * abs(gas_logz_mean), sigma=abs(gas_logz_sig), 
                                                mini=-1.5, maxi=0.0).sample()) for _ in range(set_size)]
    
    gas_logu_arr =  [float(priors.ClippedNormal(mean = -1 * abs(gas_logu_mean), sigma=abs(gas_logu_sig), 
                                                mini=-4.0, maxi=-1.0).sample()) for _ in range(set_size)]
                 
    # Fix the fburst + const > 1 issue
    for ii in np.arange(len(const_arr)):
        if const_arr[ii] + fburst_arr[ii] >= 0.95:
            f_over = (const_arr[ii] + fburst_arr[ii]) - 0.95
            if fburst_arr[ii] >= (f_over + 0.01):
                fburst_arr[ii] = fburst_arr[ii] - (f_over + 0.01)
            else:
                const_arr[ii] = const_arr[ii] - (f_over + 0.01)

    # Fixed the rest
    dust1_arr = np.full(set_size, 0.1)
    dust2_arr = np.full(set_size, 0.0)
    sf_trunc_arr = np.full(set_size, 0.0)

    # List of model parameters
    dwarf_sample_parameters = [
         {
             'dust1': dust1_arr[ii], 
             'dust2': dust2_arr[ii],
             'logzsol': logzsol_arr[ii], 
             'gas_logz': gas_logz_arr[ii], 
             'gas_logu': gas_logu_arr[ii],
             'const': const_arr[ii], 
             'tau': tau_arr[ii], 
             'tage': tage_arr[ii],
             'sf_trunc': sf_trunc_arr[ii], 
             'fburst': fburst_arr[ii], 
             'tburst': tburst_arr[ii]
         } for ii in np.arange(set_size)
    ]

    # Double check
    for ii, model in enumerate(dwarf_sample_parameters):
        if model['fburst'] + model['const'] >= 0.99:
            print(ii, model['fburst'], model['const'])
            
            
    # Initialize the spop model
    spop_tau = setup_fsps_spop(
        zcontinuous=1, imf_type=2, sfh=1, dust_type=0, 
        dust_index=-1.3, dust1_index=-1.0)

    # Get the SDSS filters
    sdss_bands = fsps.find_filter('SDSS')
    
    dwarf_sample_gaussian = generate_dwarf_population(
        spop_tau, dwarf_sample_parameters, filters=sdss_bands, n_jobs=6)


    # Measure colors and emission line EWs
    # - SDSS_EMLINES is a pre-defined dict of emission lines center wavelength and the 
    # wavelength window for measuring EW.
    # - You can save the results in a numpy array
    dwarf_sample_table = measure_color_ew(
        dwarf_sample_gaussian, em_list=SDSS_EMLINES, output=None)

    bin_size = 200

    ur_size = np.linspace( 0.0, 2.5, bin_size)
    ug_size = np.linspace( 0.0, 2.0, bin_size)
    gr_size = np.linspace(-0.1, 0.8, bin_size)
    gi_size = np.linspace(-0.2, 1.3, bin_size)
    ha_size = np.linspace( 0.0, 3.0, bin_size)
    hb_size = np.linspace(-0.5, 2.5, bin_size)
    oiii_size = np.linspace(-1.0, 3.0, bin_size)

    obs_ur = data_to_distribution(np.asarray(sdss_use['M_u'] - sdss_use['M_r']), ur_size)
    obs_ug = data_to_distribution(np.asarray(sdss_use['M_u'] - sdss_use['M_g']), ug_size)
    obs_gr = data_to_distribution(np.asarray(sdss_use['M_g'] - sdss_use['M_r']), gr_size)
    obs_gi = data_to_distribution(np.asarray(sdss_use['M_g'] - sdss_use['M_i']), gi_size)
    obs_ha = data_to_distribution(np.log10(abs(sdss_use['H_ALPHA_EQW'])), ha_size)
    obs_hb = data_to_distribution(np.log10(abs(sdss_use['H_BETA_EQW'])), hb_size)
    obs_oiii = data_to_distribution(np.log10(abs(sdss_use['OIII_5007_EQW'])), oiii_size)

    model_ur = data_to_distribution(dwarf_sample_table['ur_color'], ur_size)
    model_ug = data_to_distribution(dwarf_sample_table['ug_color'], ug_size)
    model_gr = data_to_distribution(dwarf_sample_table['gr_color'], gr_size)
    model_gi = data_to_distribution(dwarf_sample_table['gi_color'], gi_size)
    model_ha = data_to_distribution(np.log10(abs(dwarf_sample_table['ew_halpha'])), ha_size)
    model_hb = data_to_distribution(np.log10(abs(dwarf_sample_table['ew_hbeta'])), hb_size)
    model_oiii = data_to_distribution(np.log10(abs(dwarf_sample_table['ew_oiii_5007'])), oiii_size)

    obs_stack = np.transpose(np.vstack([obs_ur, obs_ug, obs_gr, 
                                        obs_gi, obs_ha, obs_hb, 
                                        obs_oiii]))

    model_stack = np.transpose(np.vstack([model_ur, model_ug, model_gr, 
                                        model_gi, model_ha, model_hb, 
                                        model_oiii]))




    total_loss = entropy(obs = obs_stack, model = model_stack)

    return total_loss



# In[6]:


best = fmin(loss_function, space, algo=tpe.suggest, max_evals = 1000)

print(space_eval(space, best))


# In[7]:



'''

space_test = [hp.uniform('x',0,9), hp.normal('y',0,1)]

def q(args):
    x,y = args
    return x**2+y**2

best_test = fmin(q,space_test, algo = rand.suggest, max_evals = 100)
print(space_eval(space_test, best_test))

'''


# In[ ]:




