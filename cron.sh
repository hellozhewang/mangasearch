#!/bin/sh
set +e  
while true  
do  
  sh commit.sh r
  echo 'Done! sleeping.....'
  sleep 3600  
done