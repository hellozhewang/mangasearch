if [ $# -gt 0 ] && [ $1 = "r" ]
then
    python3 main.py
fi

git add .
git commit -m "update"
git push origin