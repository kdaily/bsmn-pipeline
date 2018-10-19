#!/usr/bin/env python3

import argparse
import pandas as pd
import synapseclient
import subprocess
import pathlib
import os
import sys
from collections import defaultdict

cmd_home = os.path.dirname(os.path.realpath(__file__))
pipe_home = os.path.normpath(cmd_home + "/..")
util_home = pipe_home + "/analysis_utils"
job_home = cmd_home + "/job_scripts"
sys.path.append(pipe_home)

from library.job_queue import GridEngineQueue
q = GridEngineQueue()

def main():
    args = parse_args()
    samples = parse_sample_file(args.infile)
    synapse_login()
    save_run_info(args.config)
    
    for sample, sdata in samples.items():
        print(sample)
        jid_pre = submit_pre_jobs(sample, sdata)
        jid_list = []
        for ploidy in range(2,11):
            jid = submit_gatk_jobs(sample, ploidy, jid_pre)
            jid = submit_filter_jobs(sample, ploidy, jid)
            jid_list.append(jid)
        jid = ",".join(jid_list)
        submit_post_jobs(sample, jid)
        print()

def opt(sample, jid=None):
    opt = "-r y -j y -o {log_dir} -l h_vmem=4G".format(log_dir=log_dir(sample))
    if jid is not None:
        opt = "-hold_jid {jid} {opt}".format(jid=jid, opt=opt)
    return opt

def submit_pre_jobs(sample, sdata):
    jid_list = []
    for fname, synid in sdata:
        jid_list.append(
            q.submit(opt(sample), 
                "{job_home}/pre_1.download.sh {sample} {fname} {synid}".format(
                    job_home=job_home, sample=sample, fname=fname, synid=synid)))
    jid = ",".join(jid_list)
    q.submit(opt(sample, jid), 
        "{job_home}/pre_2.cnvnator.sh {sample}".format(
            job_home=job_home, sample=sample))
    return jid

def submit_gatk_jobs(sample, ploidy, jid):
    jid = q.submit(
        "-t 1-24 {opt}".format(opt=opt(sample, jid)),
        "{job_home}/gatk_1.hc_gvcf.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    jid = q.submit(
        "-t 1-24 {opt}".format(opt=opt(sample, jid)),
        "{job_home}/gatk_2.joint_gt.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    jid = q.submit(opt(sample, jid),
        "{job_home}/gatk_3.concat_vcf.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    jid = q.submit(opt(sample, jid),
        "{job_home}/gatk_4.vqsr.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    return jid

def submit_filter_jobs(sample, ploidy, jid):
    jid = q.submit(opt(sample, jid),
        "{job_home}/filter_1.known_germ_filtering.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    jid_vaf = q.submit(opt(sample, jid),
        "{job_home}/filter_2-1.vaf_info.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    jid_str = q.submit(opt(sample, jid),
        "{job_home}/filter_2-2.strand_info.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    jid = q.submit(opt(sample, jid_vaf+","+jid_str),
        "{job_home}/filter_3.bias_summary.sh {sample} {ploidy}".format(
            job_home=job_home, sample=sample, ploidy=ploidy))
    return jid

def submit_post_jobs(sample, jid):
    jid = q.submit(opt(sample, jid),
        "{job_home}/post_1.candidates.sh {sample}".format(
            job_home=job_home, sample=sample))
    return jid

def parse_args():
    parser = argparse.ArgumentParser(
        description='Variant Calling Pipeline')

    parser.add_argument(
        'infile', metavar='sample_list.txt', 
        help='Sample list file shoud have sample_id, synapse_id, and file_name.')

    parser.add_argument(
        '-c', '--config', metavar='config file',
        help='Default: [pipeline home]/pipeline.conf', 
        default="{pipe_home}/pipeline.conf".format(pipe_home=pipe_home))

    return parser.parse_args()

def parse_sample_file(sfile):
    samples = defaultdict(list)
    for sname, group in pd.read_table(sfile).groupby("sample_id"):
        for idx, sdata in group.iterrows():
            key = sname
            val = (sdata["file"], sdata["synapse_id"])
            samples[key].append(val)
    return samples
    
def synapse_login():
    try:
        synapseclient.login()
    except:
        subprocess.run(['synapse', 'login', '--remember-me'])

def save_run_info(config):
    with open("run_info", "w") as run_file:
        run_file.write("CMD_HOME={path}\n".format(path=cmd_home))
        run_file.write("UTIL_HOME={path}\n\n".format(path=util_home))
        with open(config) as cfg_file:
            for line in cfg_file:
                run_file.write(line)

def log_dir(sample):
    log_dir = sample+"/logs"
    pathlib.Path(log_dir).mkdir(parents=True, exist_ok=True)
    return log_dir

if __name__ == "__main__":
    main()