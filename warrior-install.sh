#!/bin/bash
if ! dpkg-query -Wf'${Status}' python-crypto 2>/dev/null | grep -q '^i'
then
  echo "Installing python-crypto"
  sudo apt-get update
  sudo apt-get -y install python-crypto
fi

if ! sudo pip freeze | grep -q pyamf
then
  echo "Installing pyamf"
  if ! sudo pip install pyamf
  then
    exit 1
  fi
fi

exit 0
