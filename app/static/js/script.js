document.addEventListener('DOMContentLoaded', function () {
    const searchInput = document.getElementById('search-input');
    const searchButton = document.getElementById('search-button');
    const resultsList = document.getElementById('results-list');
    const resultsCount = document.getElementById('results-count');
    const noResults = document.getElementById('no-results');
    const loading = document.getElementById('loading');
    const statsElement = document.getElementById('stats');
    const themeToggleButton = document.getElementById('theme-toggle');

    // Maximum height in pixels before collapsing a note
    const MAX_NOTE_HEIGHT = 150;

    // Theme functionality
    initializeTheme();

    // Load stats on page load
    fetchStats();

    // Add event listeners
    searchButton.addEventListener('click', performSearch);
    searchInput.addEventListener('keypress', function (e) {
        if (e.key === 'Enter') {
            performSearch();
        }
    });

    themeToggleButton.addEventListener('click', toggleTheme);

    function initializeTheme() {
        // Check for saved theme preference or respect OS preference
        const savedTheme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;

        if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
            document.documentElement.setAttribute('data-theme', 'dark');
            themeToggleButton.querySelector('.material-icons').textContent = 'light_mode';
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
            themeToggleButton.querySelector('.material-icons').textContent = 'dark_mode';
        }
    }

    function toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);

        // Update icon
        themeToggleButton.querySelector('.material-icons').textContent =
            newTheme === 'dark' ? 'light_mode' : 'dark_mode';
    }

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

            // Add similarity score badge
            const scorePercentage = Math.round(note.score * 100);
            badges += `<span class="note-badge badge-score">${scorePercentage}% match</span>`;

            // Highlight matching text in title and content
            const highlightedTitle = highlightMatches(note.title, query);
            const highlightedContent = highlightMatches(note.content, query);

            // Handle image attachments
            let attachmentsHTML = '';
            if (note.attachments && note.attachments.length > 0) {
                attachmentsHTML = '<div class="note-attachments">';
                note.attachments.forEach(attachment => {
                    if (attachment.mimetype && attachment.mimetype.startsWith('image/')) {
                        attachmentsHTML += `
                            <div class="note-image-container">
                                <img src="/api/image/${encodeURIComponent(attachment.filePath)}" 
                                     alt="Attached image" 
                                     class="note-image" 
                                     onclick="window.open(this.src, '_blank')" />
                            </div>
                        `;
                    }
                });
                attachmentsHTML += '</div>';
            }

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

            const showRelatedButton = `<button class="show-related-button" data-content="${encodeURIComponent(note.title + ' ' + note.content)}">
                <span class="material-icons">layers</span> Show related</button>`;

            card.innerHTML = `
                <div class="note-header">
                    ${badges}
                    ${highlightedTitle ? `<div class="note-title">${highlightedTitle}</div>` : ''}
                </div>
                <div class="note-content">${highlightedContent}</div>
                ${attachmentsHTML}
                ${annotations}
                <div class="note-meta">
                    <span>Created: ${note.created}</span>
                    <span>Last edited: ${note.edited}</span>
                </div>
                <div class="note-actions">
                    ${showRelatedButton}
                </div>
            `;

            resultsList.appendChild(card);

            // Check if note content is too long and needs to be collapsible
            const noteContent = card.querySelector('.note-content');
            if (noteContent && noteContent.clientHeight > MAX_NOTE_HEIGHT) {
                makeNoteCollapsible(noteContent);
            }
        });

        // Add event listeners for "Show related" buttons
        document.querySelectorAll('.show-related-button').forEach(button => {
            button.addEventListener('click', function () {
                const noteContent = decodeURIComponent(this.dataset.content);
                showRelatedNotes(noteContent);
            });
        });
    }

    function showRelatedNotes(noteContent) {
        // Use the note content as search query
        searchInput.value = noteContent
        performSearch();

        // Scroll to top of results
        window.scrollTo({
            top: document.querySelector('.search-container').offsetTop - 20,
            behavior: 'smooth'
        });
    }

    function highlightMatches(text, query) {
        if (!text) return '';

        // Escape special characters for regex
        const escapedQuery = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const regex = new RegExp(`(${escapedQuery})`, 'gi');
        return text.replace(regex, '<mark>$1</mark>');
    }

    // Function to make a note collapsible
    function makeNoteCollapsible(noteElement) {
        // Save the original content and height
        const originalContent = noteElement.innerHTML;
        const originalHeight = noteElement.scrollHeight;

        // Add collapsed class
        noteElement.classList.add('collapsed-content');

        // Create toggle button
        const toggleButton = document.createElement('button');
        toggleButton.className = 'collapse-button';
        toggleButton.innerHTML = '<span class="material-icons">expand_more</span> Read more';

        // Insert button after the note content
        noteElement.parentNode.insertBefore(toggleButton, noteElement.nextSibling);

        // Add click handler
        toggleButton.addEventListener('click', function () {
            if (noteElement.classList.contains('collapsed-content')) {
                // Expand
                noteElement.classList.remove('collapsed-content');
                this.innerHTML = '<span class="material-icons">expand_less</span> Read less';
            } else {
                // Collapse
                noteElement.classList.add('collapsed-content');
                this.innerHTML = '<span class="material-icons">expand_more</span> Read more';

                // Scroll back to the top of the note card
                noteElement.closest('.note-card').scrollIntoView({
                    behavior: 'smooth',
                    block: 'nearest'
                });
            }
        });
    }
});