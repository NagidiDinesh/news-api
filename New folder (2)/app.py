import os
import requests
import urllib.parse
from flask import Flask, request, jsonify, render_template, send_file, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from datetime import datetime, timedelta
from dateutil.parser import parse
import pdfkit
from io import BytesIO
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

app = Flask(__name__)

# Configure SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key')
db = SQLAlchemy(app)

# Set up Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Cache for API key validation
_api_key_valid = None

# User model for the database
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Initialize the database and create a default user
with app.app_context():
    try:
        db.create_all()
        if not User.query.filter_by(username='admin').first():
            user = User(username='admin')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
        if not User.query.filter_by(username='venkatan2005@gmail.com').first():
            user = User(username='venkatan2005@gmail.com')
            user.set_password('password123')
            db.session.add(user)
            db.session.commit()
    except Exception as e:
        logger.error(f"Database initialization failed: {e}", exc_info=True)

@login_manager.user_loader
def load_user(user_id):
    try:
        return User.query.get(int(user_id))
    except Exception as e:
        logger.error(f"User loading failed: {e}", exc_info=True)
        return None

# Mock police districts for Andhra Pradesh
DISTRICTS = ['Anantapur', 'Chittoor', 'East Godavari', 'Guntur', 'Krishna', 'Kurnool', 'Prakasam', 'Srikakulam', 'Visakhapatnam', 'West Godavari']

# Mock AI model for filtering and classifying news
def filter_and_classify_articles(articles, district):
    police_keywords = ['crime', 'police', 'arrest', 'theft', 'robbery', 'assault', 'public noise', 'disturbance', 'investigation']
    classified_articles = []
    try:
        for article in articles:
            content = (article.get('title', '') + ' ' + article.get('description', '')).lower()
            if any(keyword in content for keyword in police_keywords):
                category = 'Theft' if 'theft' in content else 'PublicNoise' if 'noise' in content else 'Crime'
                classified_articles.append({**article, 'category': category, 'district': district})
        return classified_articles
    except Exception as e:
        logger.error(f"Error in filter_and_classify_articles: {e}", exc_info=True)
        return []

# Generate mock articles for a district
def generate_mock_articles(district, date_str, is_related=False):
    prefix = 'Related ' if is_related else ''
    return [
        {
            'title': f'{prefix}Mock Crime Incident in {district}',
            'description': f'A {prefix.lower()}theft occurred in {district} city center.',
            'source': {'name': 'Mock News Source'},
            'publishedAt': f'{date_str}T{10 if not is_related else 14}:00:00Z',
            'url': 'http://example.com'
        },
        {
            'title': f'{prefix}Public Noise Complaint in {district}',
            'description': f'Residents reported {prefix.lower()}public noise disturbances in {district}.',
            'source': {'name': 'Mock News Source'},
            'publishedAt': f'{date_str}T{12 if not is_related else 16}:00:00Z',
            'url': 'http://example.com'
        }
    ]

# Validate Currents API key
def validate_api_key(api_key):
    global _api_key_valid
    if _api_key_valid is not None:
        logger.debug(f"Using cached API key validation: {_api_key_valid}")
        return _api_key_valid
    if not api_key or len(api_key.strip()) == 0:
        logger.error("No API key provided in .env")
        _api_key_valid = False
        return False
    try:
        url = f'https://api.currentsapi.services/v1/latest-news?language=en&apiKey={api_key}'
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if 'status' in data and data['status'] == 'ok':
            logger.debug("API key validated successfully")
            _api_key_valid = True
            return True
        logger.error(f"API key validation failed: {data.get('message', 'Unknown error')}")
        _api_key_valid = False
        return False
    except requests.RequestException as e:
        logger.error(f"API key validation failed: {str(e)}")
        _api_key_valid = False
        return False

# News API providers configuration
NEWS_API_PROVIDERS = {
    'currents': {
        'url': 'https://api.currentsapi.services/v1/search?keywords={query}&start_date={from_date}&end_date={to_date}&language=en&apiKey={api_key}',
        'key': os.getenv('SMG7jG82dC7M1JFyPvlatYcK-f89zj-3t_TWEX1iex4YjXbN')
    },
    'mock': {
        'url': None,
        'key': None
    }
}

# Fetch related articles from the past 30 days
def get_related_articles(query, from_date, to_date, district, provider='currents'):
    try:
        if provider == 'mock':
            logger.debug("Using mock articles for related articles")
            return generate_mock_articles(district, to_date, is_related=True)[:3]
        
        config = NEWS_API_PROVIDERS.get(provider)
        if not config or not config['key']:
            logger.error(f"No API key for provider {provider}")
            return generate_mock_articles(district, to_date, is_related=True)[:3]
        
        query_encoded = urllib.parse.quote(query)
        url = config['url'].format(query=query_encoded, from_date=from_date, to_date=to_date, api_key=config['key'])
        logger.debug(f"Fetching related articles from: {url}")
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        if 'status' in data and data['status'] != 'ok':
            error_message = data.get('message', 'Unknown error')
            logger.error(f"Currents API error: {error_message}")
            return generate_mock_articles(district, to_date, is_related=True)[:3]
        articles = data.get('news', [])
        normalized_articles = [
            {
                'title': article.get('title', '') or 'No Title',
                'description': article.get('description', '') or '',
                'source': {'name': article.get('author', 'Unknown') or article.get('publisher', 'Unknown')},
                'publishedAt': article.get('published', '') or 'Unknown Date',
                'url': article.get('url', '') or ''
            } for article in articles
        ]
        logger.debug(f"Fetched {len(normalized_articles)} related articles for query: {query}")
        return normalized_articles[:3]
    except requests.Timeout:
        logger.error(f"Timeout fetching related articles for query: {query}")
        return generate_mock_articles(district, to_date, is_related=True)[:3]
    except requests.RequestException as e:
        logger.error(f"Failed to fetch related articles: {e}")
        return generate_mock_articles(district, to_date, is_related=True)[:3]
    except Exception as e:
        logger.error(f"Unexpected error in get_related_articles: {e}", exc_info=True)
        return generate_mock_articles(district, to_date, is_related=True)[:3]

@app.route('/')
def login():
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def do_login():
    try:
        if request.is_json:
            data = request.get_json()
            username = data.get('username')
            password = data.get('password')
        else:
            username = request.form.get('username')
            password = request.form.get('password')
        
        if not username or not password:
            return jsonify({'success': False, 'message': 'Username and password are required'}), 400

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return jsonify({'success': True})
        return jsonify({'success': False, 'message': 'Invalid credentials'}), 401
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        return jsonify({'success': False, 'message': 'Internal server error'}), 500

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template('dashboard.html', districts=DISTRICTS)

@app.route('/fetch_news', methods=['POST'])
@login_required
def fetch_news():
    data = request.get_json()
    district = data.get('district')
    date_str = data.get('date')
    logger.debug(f"Fetch news request: district={district}, date={date_str}")
    
    try:
        selected_date = parse(date_str)
        if selected_date > datetime.now():
            logger.error("Future date provided")
            return jsonify({'error': 'Date cannot be in the future'}), 400
        selected_date_str = selected_date.strftime('%Y-%m-%d')
        from_date = (selected_date - timedelta(days=30)).strftime('%Y-%m-%d')
        
        # Use mock data if no valid API key
        api_key = os.getenv('CURRENTS_API_KEY')
        if not validate_api_key(api_key):
            logger.debug("Invalid or no API key, using mock articles")
            articles = generate_mock_articles(district, selected_date_str)
            provider = 'mock'
        else:
            provider = 'currents'
            # Try broader query with state context
            query = f'crime {district} "Andhra Pradesh"'
            query_encoded = urllib.parse.quote(query)
            url = f'https://api.currentsapi.services/v1/search?keywords={query_encoded}&start_date={from_date}&end_date={selected_date_str}&language=en&apiKey={api_key}'
            logger.debug(f"Fetching news from: {url}")
            try:
                response = requests.get(url, timeout=5)
                response.raise_for_status()
                data = response.json()
                if 'status' in data and data['status'] != 'ok':
                    error_message = data.get('message', 'Unknown error')
                    logger.error(f"Currents API error: {error_message}")
                    raise requests.HTTPError(error_message)
                articles = data.get('news', [])
                normalized_articles = [
                    {
                        'title': article.get('title', '') or 'No Title',
                        'description': article.get('description', '') or '',
                        'source': {'name': article.get('author', 'Unknown') or article.get('publisher', 'Unknown')},
                        'publishedAt': article.get('published', '') or 'Unknown Date',
                        'url': article.get('url', '') or ''
                    } for article in articles
                ]
                logger.debug(f"Fetched {len(normalized_articles)} articles")
                articles = normalized_articles
            except requests.Timeout:
                logger.error(f"Timeout fetching articles for query: {query}")
                articles = generate_mock_articles(district, selected_date_str)
                provider = 'mock'
            except requests.HTTPError as e:
                error_message = str(e)
                logger.error(f"Currents API request failed: {error_message}")
                # Fallback to generic crime query
                query = 'crime "Andhra Pradesh"'
                query_encoded = urllib.parse.quote(query)
                url = f'https://api.currentsapi.services/v1/search?keywords={query_encoded}&start_date={from_date}&end_date={selected_date_str}&language=en&apiKey={api_key}'
                logger.debug(f"Falling back to generic query: {url}")
                try:
                    response = requests.get(url, timeout=5)
                    response.raise_for_status()
                    data = response.json()
                    if 'status' in data and data['status'] != 'ok':
                        error_message = data.get('message', 'Unknown error')
                        logger.error(f"Currents API error: {error_message}")
                        raise requests.HTTPError(error_message)
                    articles = data.get('news', [])
                    normalized_articles = [
                        {
                            'title': article.get('title', '') or 'No Title',
                            'description': article.get('description', '') or '',
                            'source': {'name': article.get('author', 'Unknown') or article.get('publisher', 'Unknown')},
                            'publishedAt': article.get('published', '') or 'Unknown Date',
                            'url': article.get('url', '') or ''
                        } for article in articles
                    ]
                    logger.debug(f"Fetched {len(normalized_articles)} articles from generic query")
                    articles = normalized_articles
                except requests.Timeout:
                    logger.error(f"Timeout fetching generic query: {query}")
                    articles = generate_mock_articles(district, selected_date_str)
                    provider = 'mock'
                except requests.HTTPError as e:
                    logger.error(f"Generic query failed: {e}")
                    articles = generate_mock_articles(district, selected_date_str)
                    provider = 'mock'
            
            if not articles:
                logger.debug(f"No articles found, using mock articles for {district}")
                articles = generate_mock_articles(district, selected_date_str)
                provider = 'mock'

        classified_articles = filter_and_classify_articles(articles, district)

        for article in classified_articles:
            query = article['category']
            related_articles = get_related_articles(query, from_date, selected_date_str, district, provider=provider)
            article['related_articles'] = related_articles

        return jsonify({'articles': classified_articles, 'is_mock': provider == 'mock'})
    except ValueError as e:
        logger.error(f"Date parsing error: {e}")
        return jsonify({'error': f'Invalid date format: {e}'}), 400
    except Exception as e:
        logger.error(f"Unexpected error in fetch_news: {e}", exc_info=True)
        return jsonify({'error': f'Internal server error: {str(e)}'}), 500

@app.route('/generate_pdf', methods=['POST'])
@login_required
def generate_pdf():
    data = request.get_json()
    articles = data.get('articles', [])
    district = data.get('district')
    date = data.get('date')
    logger.debug(f"Generating PDF for district={district}, date={date}, articles={len(articles)}")

    try:
        html_report = render_template('report_template.html', articles=articles, district=district, date=date)
        pdf = pdfkit.from_string(html_report, False)
        pdf_file = BytesIO(pdf)
        pdf_file.seek(0)
        return send_file(
            pdf_file,
            download_name=f'news_digest_{district}_{date}.pdf',
            as_attachment=True,
            mimetype='application/pdf'
        )
    except Exception as e:
        logger.error(f"PDF generation failed: {e}", exc_info=True)
        return jsonify({'error': f'Failed to generate PDF: {str(e)}'}), 500

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)