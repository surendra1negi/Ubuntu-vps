# Ubuntu-vps
This is an Ubuntu ssh vps which required a secret NGROK [www.ngrok.com] and it can be run upto 6 hours (it requires openssh installed in your pc).

# Setup
First go to NGROK[www.ngrok.com] and login to your account and copy your secret key. Then fork this project to your GitHub Account and goto project's setting and create a secret which is NGROK_AUTH_TOKEN and in value paste the NGROK secrat key. Then goto action tab and Stop all previous workflows and goto last previous workflow and rerun all jobs. Then go to your NGROK account and then goto endpoints [https://dashboard.ngrok.com/cloud-edge/endpoints] and copy your url which is looks like(tcp://0.tcp.us-cal-1.ngrok.io:14306) in here remove tcp:// and separate 0.tcp.us-cal-1.ngrok.io and 14306(this is port) and then goto your terminal and run command ```ssh ubuntu@<your_endpoint_url> -p <port>```
it's looks like this ```ssh ubuntu@0.tcp.us-cal-1.ngrok.io -p 14306```
then hit enter and get ```yes``` and password is ```password```


Enjoy your VPS 🥳🥳🥳
