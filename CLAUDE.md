# Rendevu
Rendevu is a website for finding affordable vacation destinations for friends that are all flying to the same location from different places. I want to be able to search for the cheapest time to travel to a location given a duration of travel (like google flight's explore feature), hotel or vacation rental options at the destination (filtered by the total number of people coming and the number of rooms).

## Primary Language
- Python
- Javascript for website

## APIs Used

Travelpayouts / Aviasales Data API — Best free option currently available. Free to access after registering with their travel affiliate network. Includes endpoints for cheapest non-stop tickets on a route, cheapest flights per day of a given month, and cheapest flights from a city to all destinations — that last one is perfect for your "meet in the middle" logic. They also offer a GraphQL service that lets you query, for example, the three cheapest one-way tickets from an origin sorted by price for a given month. The catch: data comes from a cache of recent searches rather than live queries, so it's best for generating static/pre-rendered results.

SerpApi (Google Flights) — The most capable option for your use case. They have a Google Travel Explore API (engine=google_travel_explore) that replicates the Google Flights Explore feature — you provide a departure airport and date range and get back a list of destinations with flight prices.

Booking.com Demand API — Best option with room/guest filtering. The search endpoint accepts number_of_adults, number_of_rooms, and even exact room allocation parameters, which is exactly what your group travel app needs. Requires affiliate approval but has a sandbox for testing. 

## Core Functions

The website shoudld have a search function that allows one to enter the following for the flights.
- A list of traveler origin cities and the number of travelers coming from each city
- Parameters for each person's flights (nonstop, below X duration, etc.)
- A list of desired destination cities OR a country to visit (e.g., United States).
- The specific dates to want to visit for OR a time frame we want to visit with a selected trip type. Can be either weekend, one week, or two weeks.

For the lodging part of the search, we should be able to enter:
- The total number of rooms we will need
- What type of lodging we're looking for (hotel, vacation rental, etc.)
- The level of lodging we're looking for (1-star, rating above X, etc.)

The website should then search for the cheapest flight and booking options for the city. It should be presented as a list of city options, with total prices from X listed for each, broken down into lodging and flight cost.

Links should be available for all the listed flight optins

## Usage of APIs
Practical recommendation: Use Travelpayouts for the bulk of flight data (free, no hard query cap) and reserve SerpApi for the "explore" feature specifically, since it most closely mirrors what Google Flights Explore does.

## Hosting
- Frontend (HTML/CSS/JS): GitHub Pages (`gh-pages` branch or `/docs` folder)
- Backend (Python API server): Render.com free tier — GitHub Pages is static-only, so the Python backend is hosted on Render and called via fetch from the frontend.

## API Keys

Placeholder values — replace each with your real credentials before running.

```
TRAVELPAYOUTS_TOKEN=YOUR_TRAVELPAYOUTS_TOKEN_HERE
BOOKING_AFFILIATE_ID=YOUR_BOOKING_AFFILIATE_ID_HERE
BOOKING_API_KEY=YOUR_BOOKING_API_KEY_HERE
```

**How to obtain each key:**
- **Travelpayouts**: Register as a travel affiliate at https://travelpayouts.com → Dashboard → API → copy your token.
- **Booking.com Demand API**: Apply for the Booking.com affiliate program at https://www.booking.com/affiliate-program → once approved, access the Demand API via the affiliate dashboard.

> **Note:** SerpApi (Google Flights Explore) is reserved for a future version that supports open-ended destination discovery. The first version supports specific destination cities only, so only Travelpayouts is required for flights.

## Manual Setup Checklist

These are the one-time steps you (the developer) need to complete outside of the codebase. Complete them before deploying.

---

### 1. Create a Render Account and Link GitHub

1. Go to [render.com](https://render.com) and sign up (free).
2. In the Render dashboard, click **New → Web Service**.
3. Select **Connect a GitHub repository** and authorize Render to access your GitHub account.
4. Choose the `rendevu` repo from the list.

---

### 2. Configure the Web Service on Render

Fill in the following fields when creating the service:

| Field | Value |
|---|---|
| **Name** | `rendevu-backend` (or any name you choose) |
| **Region** | US East (or whichever is closest to your users) |
| **Branch** | `main` |
| **Root Directory** | `backend` |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| **Instance Type** | `Free` |

Click **Create Web Service**. Render will assign a URL in the format `https://rendevu-backend.onrender.com` — **save this URL**, you will need it in steps 4 and 5.

> **Free tier cold-start warning**: Render's free tier spins the server down after 15 minutes of inactivity. The first request after a period of no use will take 30–50 seconds while the server boots. This is expected behavior on the free tier.

---

### 3. Set Environment Variables on Render

In the Render dashboard for your service: **Environment → Add Environment Variable**. Add each of the following:

| Key | Value |
|---|---|
| `TRAVELPAYOUTS_TOKEN` | *(your token from the API Keys section)* |
| `BOOKING_AFFILIATE_ID` | *(your Booking.com affiliate ID)* |
| `BOOKING_API_KEY` | *(your Booking.com API key)* |
| `CLIENT_API_TOKEN` | *(a random secret you generate — see below)* |

**Generating `CLIENT_API_TOKEN`**: Run this in your terminal to generate a secure random token:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Copy the output. Set it as `CLIENT_API_TOKEN` on Render **and** as a GitHub Secret (next step).

---

### 4. Add the API Token as a GitHub Secret

The frontend needs to send this token with every request to your backend so the backend can reject calls that didn't come from your site. To keep it out of the public repo, it is injected into the JavaScript at deploy time via GitHub Actions.

1. Go to your GitHub repo → **Settings → Secrets and variables → Actions → New repository secret**.
2. Name: `RENDEVU_CLIENT_TOKEN`, Value: *(the same token you generated above)*.
3. Also add a secret named `RENDER_BACKEND_URL` with value `https://rendevu-backend.onrender.com` (your Render URL from step 2). This keeps the backend URL out of the source code as well.

The GitHub Actions deployment workflow (added to the repo in Phase 1) will substitute these secrets into the frontend JavaScript at deploy time. The source file contains placeholders (`RENDEVU_CLIENT_TOKEN_PLACEHOLDER`, `RENDER_BACKEND_URL_PLACEHOLDER`) that are never the real values — only the deployed output on GitHub Pages contains the real values.

---

### 5. Enable GitHub Pages via GitHub Actions

GitHub Pages will be published automatically by the Actions workflow whenever you push to `main`. You just need to enable the right source:

1. Go to your repo → **Settings → Pages**.
2. Under **Source**, select **GitHub Actions** (not "Deploy from a branch").
3. The first push to `main` after the workflow file is added will trigger a deployment. The site will be live at `https://<your-github-username>.github.io/rendevu`.

---

### 6. How the API Token Protection Works

This is the security model in plain terms:

- The frontend JavaScript sends an `X-API-Token: <token>` header with every request to the Render backend.
- The backend rejects any request missing this header with a `401 Unauthorized` response.
- The token value is never in the GitHub repo source — it lives in Render's environment and GitHub Secrets only.
- **What this prevents**: automated scripts or bots that find your backend URL and hammer it directly, burning through your Travelpayouts/Booking.com quota.
- **What this does not prevent**: a determined person who loads your site, opens DevTools, and reads the token from the network tab. For a personal project, this level of protection is sufficient.
- The backend also enforces CORS, which blocks browser-based requests from any domain other than your GitHub Pages URL — a complementary layer.

---

### 7. Trigger a Redeployment After Any Config Change

If you update environment variables or the `render.yaml`:
- Render backend: **Render dashboard → your service → Manual Deploy → Deploy latest commit**.
- Frontend: push any change to `main` — the GitHub Actions workflow redeploys automatically.

---

## Implementation Plan

### Phase 1 — Project Scaffold

1. Initialize the repo structure:
   ```
   rendevu/
   ├── backend/          # Python FastAPI server deployed on Render
   │   ├── main.py
   │   ├── routers/
   │   │   ├── flights.py
   │   │   └── lodging.py
   │   ├── services/
   │   │   ├── travelpayouts.py
   │   │   └── booking.py
   │   ├── models.py     # Pydantic request/response models
   │   ├── requirements.txt
   │   ├── render.yaml   # Render deployment config
   │   └── .env          # API keys (never commit this)
   └── frontend/         # Static site served by GitHub Pages
       ├── index.html
       ├── results.html
       ├── css/
       │   └── styles.css
       └── js/
           ├── search.js
           └── results.js
   ```
2. Create `backend/requirements.txt` with `fastapi`, `uvicorn`, `httpx`, `python-dotenv`, `pydantic`.
3. Create `.gitignore` to exclude `.env` and `__pycache__`.

### Phase 2 — Backend API (Render)

#### 2a. Data Models (`models.py`)
- `SearchRequest`: list of origin cities with traveler counts, list of specific destination cities, date range or trip type (weekend / 1-week / 2-week), flight constraints (nonstop, max duration), lodging preferences (rooms, type, min rating).
- `DestinationResult`: destination city, total price, per-origin flight breakdown with booking links, lodging option list.

#### 2b. Flight Service (`services/travelpayouts.py`)
- `get_cheapest_on_route(origin, destination, depart_date, return_date)` → calls Travelpayouts "cheapest tickets on route" endpoint.
- For each destination in the search: query every origin→destination pair, then aggregate: `total_flight_cost = sum(cheapest_fare[origin→dest] * travelers[origin])`.

#### 2c. Lodging Service (`services/booking.py`)
- `search_lodging(city, checkin, checkout, rooms, adults, lodging_type, min_rating)` → calls Booking.com Demand API with `number_of_rooms` and `number_of_adults` filters.
- Returns top options with price, rating, type, and booking link.

#### 2d. Search Endpoint
- `POST /api/search` → accepts `SearchRequest`, fans out flight and lodging queries across all destinations in parallel (`asyncio.gather`), returns list of `DestinationResult` sorted by total cost.

#### 2e. CORS + Render Deployment
- Enable CORS in FastAPI to allow requests from the GitHub Pages domain (`https://<username>.github.io`).
- Add `render.yaml` specifying build command (`pip install -r requirements.txt`) and start command (`uvicorn main:app --host 0.0.0.0 --port $PORT`).
- Set all API key environment variables in the Render dashboard (not in the repo).

### Phase 3 — Frontend (GitHub Pages)

#### 3a. Search Page (`index.html` + `js/search.js`)
- **Travelers section**: dynamic list — add/remove origin city rows, each with city name and traveler count.
- **Destinations section**: add/remove specific destination city inputs.
- **Dates section**: toggle between specific dates (depart + return date pickers) and trip-type selector (weekend / 1-week / 2-week) with a preferred month range.
- **Flight preferences**: nonstop only checkbox, max duration input.
- **Lodging preferences**: number of rooms, lodging type (hotel / vacation rental / any), minimum rating.
- On submit: validate inputs, POST to the Render backend `/api/search`, store response in `sessionStorage`, redirect to `results.html`.

#### 3b. Results Page (`results.html` + `js/results.js`)
- Reads results from `sessionStorage`.
- Renders a card per destination: name, total estimated cost, flight cost breakdown per origin city (with booking link for each leg), lodging options (name, price, rating, booking link).
- Sort controls: sort by total cost, flight cost, or lodging cost.

#### 3c. Styling (`css/styles.css`)
- Clean, mobile-friendly layout. Card-based results grid.

### Phase 4 — Integration & Testing

1. Integration tests for each service module using the Travelpayouts API and Booking.com sandbox.
2. End-to-end test: 2 origin cities, 2 specific destinations, fixed dates → verify all results render with correct prices and links.
3. Edge cases: one traveler, same origin and destination, no lodging results available.

### Phase 5 — Deployment

1. **Backend on Render**: Connect the GitHub repo in the Render dashboard, set environment variables (`TRAVELPAYOUTS_TOKEN`, `BOOKING_AFFILIATE_ID`, `BOOKING_API_KEY`), deploy from the `backend/` directory.
2. **Frontend on GitHub Pages**: Update the `BACKEND_URL` constant in `js/search.js` with the live Render URL. Push `frontend/` to the `gh-pages` branch (or configure the `/docs` folder in repo settings → Pages).
3. Verify CORS allows requests from `https://<username>.github.io`.
4. Add a `README.md` with local dev and deployment instructions.

### Open Questions / Decisions Needed

- [ ] Provide API keys (see API Keys section above) before implementing Phase 2.