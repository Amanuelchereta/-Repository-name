AMANCHERETA AUCTION — RENDER VERSION

Files:
- main.py
- requirements.txt
- render.yaml

Render:
1. Upload these files to a GitHub repository.
2. In Render choose New -> Blueprint.
3. Select the GitHub repository.
4. Apply.
5. Enter BOT_TOKEN when Render asks for the secret.
6. Wait for deploy.
7. Open the service logs. The bot sets its Telegram webhook automatically.

IMPORTANT:
- Use a NEW BotFather token if the old token was exposed.
- Do not put the token in GitHub.
- ADMIN_ID is 8245481401.
- The auction start time is created automatically in PostgreSQL on the first successful deployment.
- Do not run another copy of the same bot token at the same time.
- Free Render web services can spin down after 15 minutes without inbound traffic.
- Free Render Postgres is limited/temporary; for a real paid auction lasting longer than the free database period, use a paid/persistent database plan.

Bot commands:
/start
/bid
/result
/admin

Payment:
50 ETB = 1 Bid Opportunity

Bid:
1.00 - 9,999.99 ETB
minimum increment 0.01
duplicate bids allowed

Winner:
Lowest Unique Bid after the 15-day auction closes.
