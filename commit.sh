if [ $# -gt 0 ] && [ $1 = "r" ]
then
    python3 /Users/zzwang/Documents/MangaScript/mangasearch/main.py
fi

git -C /Users/zzwang/Documents/MangaScript/mangasearch add .
git -C /Users/zzwang/Documents/MangaScript/mangasearch commit -m "update"
git -C /Users/zzwang/Documents/MangaScript/mangasearch push origin