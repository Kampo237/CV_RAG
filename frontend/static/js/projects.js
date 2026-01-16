/* ==========================================
   PROJECTS PAGE - JAVASCRIPT
   Filtering, Loading from DB, Animations
   ========================================== */

// ==========================================
// Projects Manager Class
// ==========================================
class ProjectsManager {
    constructor() {
        this.container = document.getElementById('projects-container');
        this.filterBtns = document.querySelectorAll('.filter-btn');
        this.loadMoreBtn = document.getElementById('load-more-btn');
        this.currentFilter = 'all';
        this.page = 1;
        this.perPage = 6;
        this.isLoading = false;
        
        // API endpoint (à configurer selon votre backend)
        this.apiEndpoint = '/api/projects'; // Changez selon votre configuration
        
        this.init();
    }
    
    init() {
        this.setupFilters();
        this.setupLoadMore();
        this.animateOnLoad();
    }
    
    // ==========================================
    // Filter System
    // ==========================================
    setupFilters() {
        this.filterBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                // Update active state
                this.filterBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                
                // Get filter value
                this.currentFilter = btn.dataset.filter;
                
                // Filter projects
                this.filterProjects();
            });
        });
    }
    
    filterProjects() {
        const projects = this.container.querySelectorAll('.project-card-full');
        
        projects.forEach((project, index) => {
            const category = project.dataset.category;
            const shouldShow = this.currentFilter === 'all' || category === this.currentFilter;
            
            if (shouldShow) {
                project.style.display = '';
                project.style.animation = `fadeInUp 0.5s ease ${index * 0.1}s forwards`;
            } else {
                project.style.display = 'none';
            }
        });
        
        // Check if we need to show "no results" message
        this.checkEmptyState();
    }
    
    checkEmptyState() {
        const visibleProjects = this.container.querySelectorAll('.project-card-full[style*="display: none"]');
        const allProjects = this.container.querySelectorAll('.project-card-full');
        
        // Remove existing empty message
        const existingMsg = this.container.querySelector('.empty-state');
        if (existingMsg) existingMsg.remove();
        
        if (visibleProjects.length === allProjects.length) {
            const emptyState = document.createElement('div');
            emptyState.className = 'empty-state';
            emptyState.innerHTML = `
                <div class="empty-icon">📭</div>
                <h3>Aucun projet trouvé</h3>
                <p>Aucun projet ne correspond à ce filtre pour le moment.</p>
            `;
            this.container.appendChild(emptyState);
        }
    }
    
    // ==========================================
    // Load More / Pagination
    // ==========================================
    setupLoadMore() {
        if (!this.loadMoreBtn) return;
        
        this.loadMoreBtn.addEventListener('click', () => {
            this.loadMoreProjects();
        });
    }
    
    async loadMoreProjects() {
        if (this.isLoading) return;
        
        this.isLoading = true;
        this.loadMoreBtn.classList.add('loading');
        this.loadMoreBtn.innerHTML = `
            <span>Chargement...</span>
            <div class="spinner"></div>
        `;
        
        try {
            // Simulated API call - replace with actual fetch
            // const response = await this.fetchProjects();
            // this.renderProjects(response.projects);
            
            // For demo: simulate loading delay
            await new Promise(resolve => setTimeout(resolve, 1000));
            
            // Show message if no more projects
            this.loadMoreBtn.innerHTML = `
                <span>Tous les projets sont affichés</span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M20 6L9 17l-5-5"/>
                </svg>
            `;
            this.loadMoreBtn.disabled = true;
            
        } catch (error) {
            console.error('Error loading projects:', error);
            this.loadMoreBtn.innerHTML = `
                <span>Erreur de chargement</span>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <circle cx="12" cy="12" r="10"/>
                    <line x1="15" y1="9" x2="9" y2="15"/>
                    <line x1="9" y1="9" x2="15" y2="15"/>
                </svg>
            `;
        } finally {
            this.isLoading = false;
            this.loadMoreBtn.classList.remove('loading');
        }
    }
    
    // ==========================================
    // Fetch Projects from API/Database
    // ==========================================
    async fetchProjects() {
        const params = new URLSearchParams({
            page: this.page,
            per_page: this.perPage,
            category: this.currentFilter !== 'all' ? this.currentFilter : ''
        });
        
        const response = await fetch(`${this.apiEndpoint}?${params}`);
        
        if (!response.ok) {
            throw new Error('Failed to fetch projects');
        }
        
        const data = await response.json();
        this.page++;
        
        return data;
    }
    
    // ==========================================
    // Render Projects from JSON Data
    // ==========================================
    renderProjects(projects) {
        projects.forEach((project, index) => {
            const card = this.createProjectCard(project);
            card.style.animation = `fadeInUp 0.5s ease ${index * 0.1}s forwards`;
            this.container.appendChild(card);
        });
    }
    
    createProjectCard(project) {
        const article = document.createElement('article');
        article.className = 'project-card-full';
        article.dataset.category = project.category;
        article.dataset.aos = 'fade-up';
        
        article.innerHTML = `
            <div class="project-image-wrapper">
                <img src="${project.image}" alt="${project.title}" loading="lazy">
                <div class="project-overlay-full">
                    <div class="project-links">
                        ${project.github_url ? `
                            <a href="${project.github_url}" target="_blank" class="project-link-btn" title="Code source">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                                    <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
                                </svg>
                            </a>
                        ` : ''}
                        ${project.live_url ? `
                            <a href="${project.live_url}" target="_blank" class="project-link-btn" title="Voir le projet">
                                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>
                                </svg>
                            </a>
                        ` : ''}
                    </div>
                </div>
                <span class="project-category-badge">${this.getCategoryLabel(project.category)}</span>
                ${project.featured ? '<span class="project-award">⭐ Featured</span>' : ''}
            </div>
            <div class="project-content-full">
                <div class="project-meta">
                    <span class="project-date">${this.formatDate(project.date)}</span>
                    <span class="project-status ${this.getStatusClass(project.status)}">${project.status}</span>
                </div>
                <h3 class="project-title-full">${project.title}</h3>
                <p class="project-description-full">${project.description}</p>
                <div class="project-technologies">
                    ${project.technologies.map(tech => `<span class="tech-tag">${tech}</span>`).join('')}
                </div>
            </div>
        `;
        
        return article;
    }
    
    getCategoryLabel(category) {
        const labels = {
            'web': 'Web App',
            'desktop': 'Desktop',
            'ai': 'IA & RAG',
            'mobile': 'Mobile'
        };
        return labels[category] || category;
    }
    
    getStatusClass(status) {
        const classes = {
            'En production': 'status-live',
            'Complété': 'status-completed',
            'En développement': 'status-dev',
            'Récompensé': 'status-award'
        };
        return classes[status] || '';
    }
    
    formatDate(dateStr) {
        const date = new Date(dateStr);
        const options = { year: 'numeric', month: 'long' };
        return date.toLocaleDateString('fr-FR', options);
    }
    
    // ==========================================
    // Animations
    // ==========================================
    animateOnLoad() {
        const projects = this.container.querySelectorAll('.project-card-full');
        
        projects.forEach((project, index) => {
            project.style.opacity = '0';
            project.style.transform = 'translateY(30px)';
            
            setTimeout(() => {
                project.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
                project.style.opacity = '1';
                project.style.transform = 'translateY(0)';
            }, 100 + (index * 100));
        });
    }
}

// ==========================================
// Example: Load Projects from JSON file
// ==========================================
async function loadProjectsFromJSON() {
    try {
        const response = await fetch('projects-data.json');
        const data = await response.json();
        
        const manager = new ProjectsManager();
        manager.renderProjects(data.projects);
        
    } catch (error) {
        console.log('Using static projects (JSON file not found)');
    }
}

// ==========================================
// Example: Django/FastAPI Integration
// ==========================================
/*
// Django View Example:
// views.py
from django.http import JsonResponse
from .models import Project

def get_projects(request):
    page = int(request.GET.get('page', 1))
    per_page = int(request.GET.get('per_page', 6))
    category = request.GET.get('category', '')
    
    projects = Project.objects.all()
    if category:
        projects = projects.filter(category=category)
    
    start = (page - 1) * per_page
    end = start + per_page
    
    projects_list = list(projects[start:end].values())
    
    return JsonResponse({
        'projects': projects_list,
        'has_more': projects.count() > end
    })

// FastAPI Example:
// main.py
from fastapi import FastAPI, Query
from typing import Optional

@app.get("/api/projects")
async def get_projects(
    page: int = 1,
    per_page: int = 6,
    category: Optional[str] = None
):
    # Query your database here
    projects = await db.get_projects(
        skip=(page-1)*per_page,
        limit=per_page,
        category=category
    )
    return {"projects": projects, "has_more": len(projects) == per_page}
*/

// ==========================================
// Initialize on DOM Load
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    new ProjectsManager();
    
    // Optional: Load from JSON/API
    // loadProjectsFromJSON();
});

// ==========================================
// CSS Animation Keyframes (added via JS)
// ==========================================
const style = document.createElement('style');
style.textContent = `
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(30px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    .spinner {
        width: 20px;
        height: 20px;
        border: 2px solid transparent;
        border-top-color: currentColor;
        border-radius: 50%;
        animation: spin 0.8s linear infinite;
    }
    
    @keyframes spin {
        to { transform: rotate(360deg); }
    }
    
    .empty-state {
        grid-column: 1 / -1;
        text-align: center;
        padding: 4rem 2rem;
        color: var(--color-text-muted);
    }
    
    .empty-icon {
        font-size: 4rem;
        margin-bottom: 1rem;
    }
    
    .empty-state h3 {
        font-family: var(--font-display);
        font-size: 1.5rem;
        margin-bottom: 0.5rem;
        color: var(--color-text);
    }
`;
document.head.appendChild(style);
