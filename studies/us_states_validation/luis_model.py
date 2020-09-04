import numpy as np
import pandas as pd
import scipy.stats as stats
from scipy.stats import poisson
from scipy.stats import nbinom
from numpy import log as ln
from typing import Callable
from datetime import datetime, timedelta
from pathlib import Path
from tqdm import tqdm

def run_luis_model(df:pd.DataFrame, locationvar:str, CI:float, filepath:Path) -> None:

    infperiod = 4.5 # length of infectious period, adjust as needed

    # Loop through locs
    locs = df[locationvar].unique()
    returndf = pd.DataFrame()
    print(f"Estimating Luis code Rt values for each {locationvar}...")
    for loc in tqdm(locs):

        from scipy.stats import gamma # not sure why this needs to be recalled after each loc, but otherwite get a type exception
        import numpy as np
        
        locdf     = df[df[locationvar]==loc].sort_values('date')
        confirmed = list(locdf['positive_smooth'])
        dates     = list(locdf['date'])
        
        # This skips the Rt analysis for locs for which there are <10 total cases
        if (confirmed[-1] < 10.):
            continue  

        # Calculate incidence (daily change)
        dconfirmed = np.diff(confirmed)
        for ii in range(len(dconfirmed)):
            if dconfirmed[ii] < 0. : dconfirmed[ii] = 0.
            if np.isnan(dconfirmed[ii]) : dconfirmed[ii] = 0.
        xd=dates[1:]

        # Smoothing over sdays (number of days) moving window, averages large chunking in reporting in consecutive days        
        yy = np.array(dconfirmed).ravel() 
        TotalCases = np.cumsum(yy) # These are confirmed cases after smoothing: tried also a lowess smoother but was a bit more parameer dependent from place to place.

        alpha=3. # shape parameter of gamma distribution
        beta=2.  # rate parameter of gamma distribution see https://en.wikipedia.org/wiki/Gamma_distribution

        valpha=[]
        vbeta=[]

        pred=[]
        pstdM=[]
        pstdm=[]
        NewCases=[]

        predR=[]
        pstRRM=[]
        pstRRm=[]

        anomalyday=[]
        anomalypred=[]

        for i in range(2,len(TotalCases)):
            new_cases=float(TotalCases[i]-TotalCases[i-1])
            old_new_cases=float(TotalCases[i-1]-TotalCases[i-2])
            
            # This uses a conjugate prior as a Gamma distribution for b_t, with parameters alpha and beta
            alpha =alpha+new_cases
            beta=beta +old_new_cases
            valpha.append(alpha)
            vbeta.append(beta)
            
            mean = gamma.stats(a=alpha, scale=1/beta, moments='m')
            
            RRest=1.+infperiod*ln(mean)
            if (RRest<0.): RRest=0.
            predR.append(RRest)
            testRRM=1.+infperiod*ln( gamma.ppf(CI, a=alpha, scale=1./beta) ) # these are the boundaries of the CI% confidence interval  for new cases
            if (testRRM <0.): testRRM=0.
            pstRRM.append(testRRM)
            testRRm=1.+infperiod*ln( gamma.ppf(1-CI, a=alpha, scale=1./beta) )
            if (testRRm <0.): testRRm=0.
            pstRRm.append(testRRm)
                        
            if (new_cases==0. or old_new_cases==0.):
                pred.append(0.)
                pstdM.append(10.)
                pstdm.append(0.)
                NewCases.append(0.)
            
            if (new_cases>0. and old_new_cases>0.):
                NewCases.append(new_cases)
                
                # Using a Negative Binomial as the  Posterior Predictor of New Cases, given old one
                # This takes parameters r,p which are functions of new alpha, beta from Gamma
                r, p = alpha, beta/(old_new_cases+beta)
                mean, _, _, _ = nbinom.stats(r, p, moments='mvsk')
                
                pred.append(mean) # the expected value of new cases
                testciM=nbinom.ppf(CI, r, p) # these are the boundaries of the CI% confidence interval  for new cases
                testcim=nbinom.ppf(1-CI, r, p)

                if (testciM == 0) & (testcim == 0): testciM = 1

                pstdM.append(testciM)
                pstdm.append(testcim)
                
                np=p
                nr=r
                flag=0
                
                while (new_cases>testciM or new_cases<testcim):
                    if (flag==0):
                        anomalypred.append(new_cases)
                        anomalyday.append(dates[i+1]) # the first new cases are at i=2
                    
                    # annealing: increase variance so as to encompass anomalous observation: allow Bayesian code to recover
                    # mean of negbinomial=r*(1-p)/p  variance= r (1-p)/p**2
                    # preserve mean, increase variance--> np=0.8*p (smaller), r= r (np/p)*( (1.-p)/(1.-np) )
                    # test anomaly
                    
                    nnp=0.95*np # this doubles the variance, which tends to be small after many Bayesian steps
                    nr= nr*(nnp/np)*( (1.-np)/(1.-nnp) ) # this assignement preserves the mean of expected cases
                    np=nnp
                    mean, var, skew, kurt = nbinom.stats(nr, np, moments='mvsk')
                    testciM=nbinom.ppf(CI, nr, np)
                    testcim=nbinom.ppf(1-CI, nr, np)
                    
                    flag=1
                else:
                    if (flag==1):
                        alpha=nr  # this updates the R distribution  with the new parameters that enclose the anomaly
                        beta=np/(1.-np)*old_new_cases
                        
                        testciM=nbinom.ppf(CI, nr, np)
                        testcim=nbinom.ppf(1-CI, nr, np)
                        
                        # annealing leaves the RR mean unchanged, but we need to adjus its widened CI:
                        testRRM=1.+infperiod*ln( gamma.ppf(CI, a=alpha, scale=1./beta) )# these are the boundaries of the CI% confidence interval  for new cases
                        if (testRRM <0.): testRRM=0.
                        testRRm=1.+infperiod*ln( gamma.ppf(1-CI, a=alpha, scale=1./beta) )
                        if (testRRm <0.): testRRm=0.
                        
                        pstRRM=pstRRM[:-1] # remove last element and replace by expanded CI for RRest
                        pstRRm=pstRRm[:-1]
                        pstRRM.append(testRRM)
                        pstRRm.append(testRRm)

        # visualization of the time evolution of R_t with confidence intervals
        x=[]
        for i in range(len(predR)):
            x.append(i)
        days=dates[3:]
        xd=days
        dstr=[]
        for xdd in xd:
            dstr.append(xdd.strftime("%Y-%m-%d"))
            
            
        appenddf = pd.DataFrame({locationvar:loc,
                                 'date':days,
                                 'RR_pred_luis':predR,
                                 'RR_CI_lower_luis':pstRRm,
                                 'RR_CI_upper_luis':pstRRM})
        returndf = pd.concat([returndf,appenddf], axis=0) 
        
    returndf.to_csv(filepath/"luis_code_estimates.csv", index=False)