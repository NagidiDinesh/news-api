document.getElementById('login-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const username = document.getElementById('username').value;
    const password = document.getElementById('password').value;
    const errorMessage = document.getElementById('error-message');

    try {
        const response = await fetch('/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const result = await response.json();
        if (result.success) {
            window.location.href = '/dashboard';
        } else {
            errorMessage.textContent = result.message || 'Login failed';
        }
    } catch (error) {
        errorMessage.textContent = 'An error occurred';
    }
});