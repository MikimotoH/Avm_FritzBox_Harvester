from os import path
import sys
import re
import ftputil
import pdb
import os
import psycopg2
from glob import glob
from datetime import datetime
from web_utils import getFileSha1, getFileMd5
import traceback
import time
from infix_operator import Infix


store_dir='output/avm/'


def path_join_func(dir, fname):
    return os.path.join(dir,fname)
pjoin = Infix(path_join_func)


def parse_info_txt(fname):
    lang2cc = {
        'german': 'de',
        'deutsch': 'de',
        'english': 'en',
        'englisch': 'en',
        'french': 'fr',
        'französisch': 'fr',
        'italian': 'it',
        'italienisch': 'it',
        'polish':'pl',
        'polnisch':'pl',
        'spanish':'es',
        'spanisch': 'es',
    }
    with open(fname, mode='r', encoding='latin2', errors='ignore') as fin:
        lines = fin.read().splitlines()
    model=''
    version=''
    rel_date=None
    annex=''
    lang=''
    for l in lines:
        l = l.strip()
        if not l:
            continue
        if l.startswith('__'):
            break
        if not l[0].isalpha():
            continue
        if ':' not in l:
            continue
        try:
            aname, avalue = l.split(':')
        except ValueError:
            try:
                aname,_,avalue = l.split(':')
            except ValueError:
                continue
        aname=aname.lower().strip()
        avalue = avalue.strip(" \t\n.-").replace('-', ' ')
        if not avalue:
            continue
        if aname in ['product', 'produkt']:
            model = avalue
        elif aname in ['version']:
            version = avalue.lstrip('0')
        elif aname in ['release date', 'release datum']:
            avalue = re.sub(r'\.|-', '/', avalue)
            rel_date = datetime.strptime(avalue, '%d/%m/%Y')
        elif aname in ['language', 'sprache']:
            lang = ','.join(lang2cc[_.strip().lower()] for _ in avalue.split(',') if _.strip())
        elif aname in ['annex']:
            annex = avalue
        else:
            # print('unknown attribute name:"%s"'%aname)
            continue
        if model and version and rel_date:
            break
    assert model and version

    if lang:
        version = version + ' Language:'+lang
    elif annex:
        version = version + ' Annex:'+annex
    elif lang and annex:
        version = version + ' Language:'+lang + ' Annex:'+annex
    return model, version, rel_date


def upsert_psql(file_name, fw_url, model, version, rel_date):
    try:
        conn = psycopg2.connect(database="firmware", user="firmadyne",
                                password="firmadyne", host="127.0.0.1")
        cur = conn.cursor()
        brand_id=1
        file_sha1 = getFileSha1(file_name)
        file_md5 = getFileMd5(file_name)
        file_size = os.path.getsize(file_name)
        cur.execute("INSERT INTO image \
                    (filename, brand, model, version, rel_date, brand_id, \
                    file_size, hash, file_sha1, file_url) VALUES \
                    (      %s,    %s,    %s,      %s,       %s,       %s, \
                           %s,   %s,        %s,       %s)",
                    (file_name, 'Avm', model, version, rel_date, brand_id,
                     file_size, file_md5, file_sha1, fw_url))
        conn.commit()
    finally:
        conn.close()


def get_ext(fname):
    return path.splitext(fname)[-1]


os.makedirs(store_dir, exist_ok=True)
with ftputil.FTPHost('ftp.avm.de', 'anonymous', '') as host:
    host.keep_alive()
    for root, dirs, files in host.walk('fritz.box'):
        if not any(_ for _ in files if get_ext(_)=='.image'):
            continue
        files.sort(key=lambda x:get_ext(x))
        for f in files:
            ext = get_ext(f)
            if ext !='.image':
                continue
            if path.exists(store_dir/pjoin/f) and \
                    host.path.getsize(root/pjoin/f) == path.getsize(store_dir/pjoin/f) and \
                    time.time() - path.getmtime(store_dir/pjoin/f) < 3600*24*7:
                print('bypass download firmware: %s'%f)
            else:
                print('download %s/%s'%(root,f))
                host.download(root/pjoin/f, store_dir/pjoin/f)
            if host.path.exists(root/pjoin/'info.txt'):
                host.download(root/pjoin/'info.txt', store_dir/pjoin/'info.txt')
                model, version, rel_date = parse_info_txt(store_dir/pjoin/'info.txt')
            if 'model' not in locals().keys() or not model:
                model = path.splitext(f)[0]
            if 'version' not in locals().keys() or not version:
                version = f
            if 'rel_date' not in locals().keys() or not rel_date:
                rel_date = host.path.getmtime(root/pjoin/f)
                rel_date = datetime.fromtimestamp(rel_date)
            fw_url='ftp://ftp.avm.de'/pjoin/root/pjoin/f
            upsert_psql(store_dir/pjoin/f, fw_url, model, version, rel_date)


