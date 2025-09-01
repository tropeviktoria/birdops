# birdops
Get alerted for specific bird species matches in London (Southfields) within a 15km radius.
This script will send alerts to your chosen slack channel and google sheets file - only if there have been any new sighting since the last alert. 
If not, it will simply not return anything in your google sheet and send a "now new sightings" message on Slack.

You can also follow these steps to automate this script, so it runs every 15mins:

1. Open your crontab in terminal and enter this command:

crontab -e

2. Follow with these lines (replace <you> to match your path):

SHELL=/bin/zsh
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
*/15 * * * * cd /Users/<you>/Documents/birdops && /Users/<you>/Documents/birdops/.venv/bin/python /Users/<you>/Documents/birdops/birdops.py >> /Users/<you>/Documents/birdops/run.log 2>&1

3. Very it has been saved (this should return the same three lines mentioned above)

crontab -l

4. The script will now run every 15min unless your mac is asleep.
