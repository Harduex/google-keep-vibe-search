document.addEventListener('DOMContentLoaded', function() {
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');
    const resultsList = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');
    const noResults = document.getElementById('no-results');
    const loading = document.getElementById('loading');
    const statsElement = document.getElementById('stats');
    
    // Load stats on page load
    fetchStats();
    
    // Add event listeners
    searchButton.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });
    
    function fetchStats() {
        fetch('/api/stats')
            .then(response => response.json())
            .then(data => {
                document.getElementById('total-notes').textContent = data.total_notes;
                
                const statsText = [];
                if (data.archived_notes > 0) {
                    statsText.push(`${data.archived_notes} archived`);
                }
                if (data.pinned_notes > 0) {
                    statsText.push(`${data.pinned_notes} pinned`);
                }
                
                if (statsText.length > 0) {
                    statsElement.textContent = `${data.total_notes} notes loaded (${statsText.join(', ')})`;
                } else {
                    statsElement.textContent = `${data.total_notes} notes loaded`;
                }
            })
            .catch(error => {
                console.error('Error fetching stats:', error);
                statsElement.textContent = 'Error loading notes stats';
            });
    }
    
    function performSearch() {
        const query = searchInput.value.trim();
        if (!query) return;
        
        // Show loading
        resultsList.innerHTML = '';
        resultsCount.textContent = '';
        noResults.classList.add('hidden');
        loading.classList.remove('hidden');
        
        fetch(`/api/search?q=${encodeURIComponent(query)}`)
            .then(response => response.json())
            .then(data => {
                loading.classList.add('hidden');
                
                if (data.results && data.results.length > 0) {
                    displayResults(data.results, query);
                } else {
                    noResults.classList.remove('hidden');
                }
            })
            .catch(error => {
                console.error('Error searching notes:', error);
                loading.classList.add('hidden');
                resultsCount.textContent = 'Error searching notes. Please try again.';
            });
    }
    
    function displayResults(results, query) {
        resultsCount.textContent = `Found ${results.length} matching note${results.length === 1 ? '' : 's'}`;
        
        resultsList.innerHTML = '';
        results.forEach(note => {
            const card = document.createElement('div');
            card.className = `note-card ${note.color !== 'DEFAULT' ? 'color-' + note.color : ''}`;
            
            let badges = '';
            if (note.pinned) {
                badges += '<span class="note-badge badge-pinned">Pinned</span>';
            }
            if (note.archived) {
                badges += '<span class="note-badge badge-archived">Archived</span>';
            }
            
            // Highlight matching text in title and content
            const highlightedTitle = highlightMatches(note.title, query);
            const highlightedContent = highlightMatches(note.content, query);
            
            let annotations = '';
            if (note.annotations && note.annotations.length > 0) {
                let annotationItems = '';
                note.annotations.forEach(annotation => {
                    if (annotation.url) {
                        annotationItems += `<span class="annotation"><a href="${annotation.url}" target="_blank">${annotation.title || annotation.url}</a></span>`;
                    }
                });
                
                if (annotationItems) {
                    annotations = `
                        <div class="note-annotations">
                            ${annotationItems}
                        </div>
                    `;
                }
            }
            
            card.innerHTML = `
                <div class="note-header">
                    ${badges}
                    ${highlightedTitle ? `<div class="note-title">${highlightedTitle}</div>` : ''}
                </div>
                <div class="note-content">${highlightedContent}</div>
                ${annotations}
                <div class="note-meta">
                    <span>Created: ${note.created}</span>
                    <span>Last edited: ${note.edited}</span>
                </div>
            `;
            
            resultsList.appendChild(card);
        });
    }
    
    function highlightMatches(text, query) {
        if (!text) return '';
        
        // Escape special characters for regex
        const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedQuery})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }
});