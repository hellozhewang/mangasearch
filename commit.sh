if [ $# -gt 0 ] && [ $1 = "r" ]
then
    python3 /home/zzwang/mangasearch/src/main.py
fi

git -C /home/zzwang/mangasearch/src add .
git -C /home/zzwang/mangasearch/src commit -m "update"
git -C /home/zzwang/mangasearch/src push origin