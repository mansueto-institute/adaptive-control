from pathlib import Path

import flat_table
import numpy as np
import pandas as pd
from adaptive.etl.commons import download_data
from adaptive.etl.covid19india import (data_path, get_time_series,
                                       load_all_data, state_code_lookup)
from adaptive.smoothing import notched_smoothing

data = Path("./data").resolve()

# Rt estimation parameters
CI = 0.95
window = 14
gamma = 0.2
infectious_period = 5
smooth = notched_smoothing(window)

# simulation parameters
simulation_start = pd.Timestamp("Jan 1, 2021")
num_sims = 10000

# common vaccination parameters
immunity_threshold = 0.75 

#################################################################


# load covid19 india data 
print(":: loading case timeseries data")
# download_data(data, 'timeseries.json', "https://api.covid19india.org/v3/")
with (data/'timeseries.json').open("rb") as fp:
    df = flat_table.normalize(pd.read_json(fp)).fillna(0)
df.columns = df.columns.str.split('.', expand = True)
dates = np.squeeze(df["index"][None].values)
df = df.drop(columns = "index").set_index(dates).stack([1, 2]).drop("UN", axis = 1)


print(":: loading admin data")
# load admin data on population
IN_age_structure = { # WPP2019_POP_F01_1_POPULATION_BY_AGE_BOTH_SEXES
    "0-17":   116880 + 117982 + 126156 + 126046,
    "18-29":  122505 + 117397,
    "30-39":  112176 + 103460,
    "40-49":   90220 +  79440,
    "50-59":   68876 +  59256,
    "60-69":   48891 +  38260,
    "70+":     24091 +  15084 +   8489 +   3531 + 993 + 223 + 48,
    # 0:  116_880,
    # 5:  117_982 + 126_156 + 126_046,
    # 18: 122_505 + 117_397, 
    # 30: 112_176 + 103_460,
    # 40: 90_220 + 79_440,
    # 50: 68_876 + 59_256 + 48_891,
    # 65: 38_260 + 24_091,
    # 75: 15_084 + 8_489 + 3_531 +  993 +  223 +  48,
}

district_populations = { 
    'Ariyalur'       :   754_894, # 'Ariyalur'
    'Chengalpattu'   : 2_556_244, # 'Chengalpattu'
    'Chennai'        : 4_646_732, # 'Chennai'
    'Coimbatore'     : 3_458_045, # 'Coimbatore'
    'Cuddalore'      : 2_605_914, # 'Cuddalore'
    'Dharmapuri'     : 1_506_843, # 'Dharmapuri'
    'Dindigul'       : 2_159_775, # 'Dindigul'
    'Erode'          : 2_251_744, # 'Erode'
    'Kallakurichi'   : 1_370_281, # 'Kallakurichi'
    'Kancheepuram'   : 1_166_401, # 'Kanchipuram'
    'Kanyakumari'    : 1_870_374, # 'Kanniyakumari'
    'Karur'          : 1_064_493, # 'Karur'
    'Krishnagiri'    : 1_879_809, # 'Krishnagiri'
    'Madurai'        : 3_038_252, # 'Madurai'
    # 'Mayiladuthurai' :   918_356, # 'Mayiladuthurai'
    'Nagapattinam'   :   697_069, # 'Nagapattinam'
    'Namakkal'       : 1_726_601, # 'Namakkal'
    'Nilgiris'       :   735_394, # 'Nilgiris'
    'Perambalur'     :   565_223, # 'Perambalur'
    'Pudukkottai'    : 1_618_345, # 'Pudukkottai'
    'Ramanathapuram' : 1_353_445, # 'Ramanathapuram'
    'Ranipet'        : 1_210_277, # 'Ranipet'
    'Salem'          : 3_482_056, # 'Salem'
    'Sivaganga'      : 1_339_101, # 'Sivagangai'
    'Tenkasi'        : 1_407_627, # 'Tenkasi'
    'Thanjavur'      : 2_405_890, # 'Thanjavur'
    'Theni'          : 1_245_899, # 'Theni'
    'Thiruvallur'    : 3_728_104, # 'Tiruvallur'
    'Thiruvarur'     : 1_264_277, # 'Tiruvarur'
    'Thoothukkudi'   : 1_750_176, # 'Thoothukudi'
    'Tiruchirappalli': 2_722_290, # 'Tiruchirappalli'
    'Tirunelveli'    : 1_665_253, # 'Tirunelveli'
    'Tirupathur'     : 1_111_812, # 'Tirupattur'
    'Tiruppur'       : 2_479_052, # 'Tiruppur'
    'Tiruvannamalai' : 2_464_875, # 'Tiruvannamalai'
    'Vellore'        : 1_614_242, # 'Vellore'
    'Viluppuram'     : 2_093_003, # 'Viluppuram'
    'Virudhunagar'   : 1_942_288, # 'Virudhunagar'
}

# laxminarayan contact matrix 
laxminarayan_contact_matrix = np.array([
    # [89 + 452, 1358, 1099, 716, 821, 297, 80+15],
    # [431 + 3419, 8600, 7131, 5188, 5181, 1876, 502+67],
    [4391, 9958, 8230, 5904, 6002, 2173, 664],
    [1882 + 11179, 41980, 29896, 23127, 22914, 7663, 1850+228],
    [2196 + 13213, 35625, 31752, 21777, 22541, 7250, 1796+226],
    [1097 + 9768, 27701, 23371, 18358, 17162, 6040, 1526+214],
    [1181 + 8314, 26992, 22714, 17886, 18973, 6173, 1633+217],
    [358 + 2855, 7479, 6539, 5160, 5695, 2415, 597+82],
    [75+15 + 693+109, 2001+282, 1675+205, 1443+178, 1482+212, 638+72, 211+18+15+7]
])

# normalize
age_structure_norm = sum(IN_age_structure.values())
IN_age_ratios = np.array([v/age_structure_norm for v in IN_age_structure.values()])
split_by_age = lambda v: (v * IN_age_ratios).astype(int)

# from Karnataka
COVID_age_ratios = np.array([0.01618736, 0.07107746, 0.23314877, 0.22946212, 0.18180406, 0.1882451 , 0.05852026, 0.02155489])

india_pop = pd.read_csv(data/"india_pop.csv", names = ["state", "population"], index_col = "state").to_dict()["population"]

# download district-level data 
paths = {"v3": [data_path(i) for i in (1, 2)], "v4": [data_path(i) for i in range(3, 22)]}
# for target in paths['v3'] + paths['v4']: download_data(data, target)
ts = load_all_data(v3_paths = [data/filepath for filepath in paths['v3']],  v4_paths = [data/filepath for filepath in paths['v4']])\
    .query("detected_state == 'Tamil Nadu'")\
    .pipe(lambda _: get_time_series(_, "detected_district"))\
    .drop(columns = ["date", "time", "delta", "logdelta"])\
    .rename(columns = {
        "Deceased":     "dD",
        "Hospitalized": "dT",
        "Recovered":    "dR"
    })

print(":: seroprevalence scaling")
TN_sero_breakdown = np.array([0.311, 0.311, 0.320, 0.333, 0.320, 0.272, 0.253]) # from TN sero, assume 0-18 sero = 18-30 sero
TN_pop = india_pop["Tamil Nadu"]
TN_seropos = split_by_age(TN_pop) @ TN_sero_breakdown/TN_pop

(state, date, seropos, sero_breakdown) = ("TN", "October 23, 2020", TN_seropos, TN_sero_breakdown)
N = india_pop[state_code_lookup[state].replace("&", "and")]
