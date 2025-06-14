document.getElementById('fetch-news').addEventListener('click', async () => {
    const district = document.getElementById('district').value;
    const date = document.getElementById('date').value;
    const errorMessage = document.getElementById('error-message');
    const newsBody = document.getElementById('news-body');
    const downloadButton = document.getElementById('download-pdf');

    // Validate inputs
    if (!district) {
        errorMessage.textContent = 'Please select a district';
        return;
    }
    if (!date) {
        errorMessage.textContent = 'Please select a date';
        return;
    }
    // Basic date format validation (expects YYYY-MM-DD)
    const dateRegex = /^\d{4}-\d{2}-\d{2}$/;
    if (!dateRegex.test(date)) {
        errorMessage.textContent = 'Invalid date format (use YYYY-MM-DD)';
        return;
    }
    // Prevent future dates (use IST)
    const selectedDate = new Date(date + 'T23:59:59+05:30'); // End of day in IST
    const today = new Date();
    if (selectedDate > today) {
        errorMessage.textContent = 'Date cannot be in the future';
        return;
    }

    try {
        errorMessage.textContent = 'Fetching news...';
        const requestPayload = { district, date };
        console.log('Fetch news request:', requestPayload);
        const response = await fetch('/fetch_news', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestPayload),
            signal: AbortSignal.timeout(15000) // Increased to 15 seconds
        });

        let errorText = '';
        try {
            errorText = await response.text();
            console.log('Fetch news response:', errorText);
        } catch (e) {
            errorText = 'No response body';
        }

        if (!response.ok) {
            let userMessage = 'Failed to fetch news. Please try again later.';
            try {
                const errorData = JSON.parse(errorText);
                if (errorData.error) {
                    userMessage = errorData.error;
                }
            } catch (e) {
                // Not JSON
            }
            throw new Error(userMessage);
        }

        const result = JSON.parse(errorText);
        if (result.error) {
            errorMessage.textContent = `Server error: ${result.error}`;
            newsBody.innerHTML = '';
            downloadButton.style.display = 'none';
            return;
        }

        if (!result.articles || result.articles.length === 0) {
            errorMessage.textContent = 'No articles found for the selected district and date.';
            newsBody.innerHTML = '';
            downloadButton.style.display = 'none';
            return;
        }

        if (result.is_mock) {
            errorMessage.textContent = `No real articles found for ${district}. Displaying sample data. Please verify your Currents API key in .env (get a free key at https://currentsapi.services/en).`;
        } else {
            errorMessage.textContent = 'Articles loaded successfully.';
        }

        newsBody.innerHTML = '';
        result.articles.forEach(article => {
            const row = document.createElement('tr');
            const sourceName = article.source?.name || 'Unknown Source';
            const publishedAt = article.publishedAt || 'Unknown Date';
            const relatedArticles = (article.related_articles || []).map(rel => 
                `<div><a href="${rel.url || '#'}" target="_blank">${rel.title || 'No Title'}</a> (${rel.source?.name || 'Unknown Source'}, ${rel.publishedAt || 'Unknown Date'})</div>`
            ).join('');
            
            row.innerHTML = `
                <td><a href="${article.url || '#'}" target="_blank">${article.title || 'No Title'}</a></td>
                <td>${article.category || 'Unknown'}</td>
                <td>${sourceName}</td>
                <td>${publishedAt}</td>
                <td>${relatedArticles || 'None'}</td>
            `;
            newsBody.appendChild(row);
        });

        downloadButton.style.display = result.articles.length ? 'block' : 'none';
        downloadButton.onclick = async () => {
            try {
                errorMessage.textContent = 'Generating PDF...';
                const pdfPayload = { articles: result.articles, district, date };
                console.log('Generate PDF request:', pdfPayload);
                const pdfResponse = await fetch('/generate_pdf', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(pdfPayload),
                    signal: AbortSignal.timeout(15000)
                });

                let pdfErrorText = '';
                try {
                    pdfErrorText = await pdfResponse.text();
                    console.log('PDF response:', pdfErrorText);
                } catch (e) {
                    pdfErrorText = 'No response body';
                }

                if (!pdfResponse.ok) {
                    let userMessage = 'Failed to generate PDF. Please try again later.';
                    try {
                        const pdfError = JSON.parse(pdfErrorText);
                        if (pdfError.error) {
                            userMessage = `PDF generation failed: ${pdfError.error}`;
                        }
                    } catch (e) {
                        // Not JSON
                    }
                    throw new Error(userMessage);
                }

                const blob = await pdfResponse.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `news_digest_${district}_${date}.pdf`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                errorMessage.textContent = 'PDF downloaded successfully';
            } catch (pdfError) {
                errorMessage.textContent = pdfError.message;
                console.error('PDF Error:', pdfError);
            }
        };
    } catch (error) {
        errorMessage.textContent = error.name === 'TimeoutError' 
            ? 'Request timed out. Please check your internet connection or try again later.'
            : `Error: ${error.message}`;
        console.error('Fetch News Error:', error);
        newsBody.innerHTML = '';
        downloadButton.style.display = 'none';
    }
});