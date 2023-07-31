from pathlib import Path
from datetime import datetime
from utils.logger import logger
from consts.mirna_utils import MIRBASE_FILE
from consts.global_consts import DUPLEX_DICT
from utils.utilsfile import read_csv, to_csv
import pandas as pd
import numpy as np
from utils.utilsfile import *
from consts.global_consts import ROOT_PATH, DATA_PATH, NEGATIVE_DATA_PATH, MERGE_DATA, DATA_PATH_INTERACTIONS
from duplex.ViennaDuplex import ViennaDuplex
from duplex.ViennaDuplex import *
import random
from features.SeedFeatures import *
# import MirBaseUtils.mirBaseUtils as MBU
import mirna_utils.mirbase as MBU
from multiprocessing import Process
from consts.global_consts import CONFIG
from duplex.Duplex import Duplex
import random

def valid_negative_seq(mir, mrna):
    duplex_cls: Duplex = DUPLEX_DICT['ViennaDuplex']
    logger.info(f"{ViennaDuplex} do_duplex")
    dp = duplex_cls.fromChimera(mir, mrna)
    try:
        canonic_seed = dp.canonical_seed
        non_canonic_seed = dp.noncanonical_seed

    except SeedException:
        canonic_seed = False
        non_canonic_seed = False

    # warning: number of pair was before to interactions count
    duplex = RNA.duplexfold(mir, mrna)
    MEF_duplex = duplex.energy
    site = dp.site[::-1]
    # print(MEF_duplex)

    return canonic_seed, non_canonic_seed, dp.interaction_count, MEF_duplex, site


def generate_negative_seq(orig_mirna, full_mrna, num_of_tries=10000):
    canonic_seed, non_canonic_seed, num_of_pairs, MEF_duplex, site = valid_negative_seq(orig_mirna, full_mrna)
    cond1 = canonic_seed
    cond2 = non_canonic_seed
    if cond1 or cond2:
        properties = {
            "mock_mirna": orig_mirna,
            "full_mrna": full_mrna,
            "canonic_seed": canonic_seed,
            "non_canonic_seed": non_canonic_seed,
            "num_of_pairs": num_of_pairs,
            "MEF_duplex": MEF_duplex,
            "site": site
        }
        return True, properties
    return False, {}

def generate_negative_seq_2(orig_mirna, full_mrna, num_of_tries=10000):
    canonic_seed, non_canonic_seed, num_of_pairs, MEF_duplex, site = valid_negative_seq(orig_mirna, full_mrna)

    properties = {
            "mock_mirna": orig_mirna,
            "full_mrna": full_mrna,
            "canonic_seed": canonic_seed,
            "non_canonic_seed": non_canonic_seed,
            "num_of_pairs": num_of_pairs,
            "MEF_duplex": MEF_duplex,
            "site": site
        }
    return True, properties


def sub_without_site(full_mrna, start, end, site):
    sub = full_mrna[:int(start) - 1] + full_mrna[int(end):]
    # full_nre = sub[:int(start)-1] + site[:] +sub[int(start)-1:]
    return sub


def sub_insert_NNN(full_mrna, start, end):
    start = int(start)
    orig = len(full_mrna)

    while start != end + 1:
        full_mrna = full_mrna[:start] + "N" + full_mrna[start + 1:]
        start += 1
    return full_mrna


def worker(fin, fout_name, tmp_dir):
    print("##################NEW FILE#################################")
    print(fin)
    fout = filename_suffix_append(fout_name, "_negative")
    in_df = read_csv(fin)
    in_df.rename(columns={'miRNA ID': 'miRNA_ID'}, inplace=True)

    # Gene_ID --> Gene + Transcript
    gruop_rows = in_df.groupby(['Gene_ID', "miRNA_ID"])
    group = list(gruop_rows.groups)
    count = 0
    i = 0

    neg_df = pd.DataFrame()
    for g in group:
        i += 1

        mirna_name = g[1]
        mrna_name = g[0]
        rows_group = in_df[(in_df['Gene_ID'] == mrna_name)]
        # get all the rows of this subset of interactions with the same mirna and mrna
        rows_group = rows_group[rows_group["miRNA_ID"] == mirna_name]


        full_mrna = rows_group.iloc[0]["sequence"]
        mrna_cut = rows_group.iloc[0]["sequence"]
        extra_chars = 10
        # cut all site from mrna that interact with this microRNA
        # we mask the duplex site don't the fragment
        for index, row in rows_group.iterrows():
            # mask the extent site

            start = max(0, int(row['start']) - extra_chars)
            end = min(len(full_mrna), int(row['end']) + extra_chars)
            mrna_cut = sub_insert_NNN(mrna_cut,start, end)

        print(f"$$$$$$$$$$$$$$$ {i} $$$$$$$$$$$$$$$$$$4")
        global_count = 0
        # cut_mrna = row['cut_mrna']
        cut_mrna = mrna_cut
        size_param = 40
        new_row = pd.Series()
        dict_windows = dict()
        dict_energy= dict()

        for window in range(0, len(cut_mrna) + size_param, size_param):
            global_count += 1
            sub_mrna = cut_mrna[window:window+75]
            if "N" in sub_mrna:
                global_count -=1
                continue

            valid, properties = generate_negative_seq(row['miRNA sequence'], sub_mrna)
            if not valid:
                global_count -=1
                continue

            new_row = pd.Series()
            new_row['paper name'] = row['paper name']
            new_row['organism'] = row['organism']
            new_row['miRNA ID'] = row.miRNA_ID
            new_row['miRNA sequence'] = properties["mock_mirna"]
            new_row['Gene_ID'] = row.Gene_ID
            new_row['full_mrna'] = row.sequence
            new_row['site'] = sub_mrna
            dict_energy[global_count] = properties["MEF_duplex"]
            dict_windows[global_count] = new_row

        if len(dict_windows) == 0:
            count +=1
            print("not found interaction for",i ," dataset:", fout_name)
            continue

        sort_dict = dict(sorted(dict_energy.items(), key=lambda item: item[1]))
        # top 25 keys index
        slice = int(len(sort_dict)/5) + 1
        # save the top 25 after sotr
        values = list(sort_dict.keys())[:slice]
        #chose one key
        random_value = random.choice(values)

        # values = list(dict_energy.values())
        # #
        # # # Sort the list of values
        # sorted_values = sorted(values)
        #
        # # Calculate the median value
        # n = len(sorted_values)
        # if n % 2 == 0:
        #     median_value = sorted_values[n // 2 - 1]
        # else:
        #     median_value = sorted_values[n // 2]
        #
        # # Iterate through the dictionary and find the key(s) that correspond to the median value
        # median_keys = []
        # for key, value in dict_energy.items():
        #     if value == median_value:
        #         median_keys.append(key)

        # neg_df = neg_df.append(dict_windows[median_keys[0]], ignore_index=True)
        neg_df = neg_df.append(dict_windows[random_value], ignore_index=True)

        # if i > 4:
        #     break

    #######################
    # Save df to CSV
    #######################
    neg_df.reset_index(drop=True, inplace=True)
    drop_unnamed_col(neg_df)
    neg_df["key"] = neg_df.reset_index().index
    fout = tmp_dir / fout
    to_csv(neg_df, fout)
    print("save:", fout)
    print(neg_df.shape)
    print(neg_df)

    print("The number of interacrtion that not  founf:", count)


def main():
    file_name = MERGE_DATA / "positive_interactions_new/featuers_step/"
    tmp_base = ROOT_PATH / "generate_interactions/non_overlapping_sites/"
    print("tmp:", tmp_base)
    files = list(file_name.glob('**/*.csv'))
    for p in files:
        if "darnell" not in p.stem:
            continue
        print(p)
        fout_name = "top_20_percent_" + p.name.split('.csv')[0] + '.csv'
        worker(p, fout_name, tmp_base)
        break
#
# main()