/* ==========================================
   Modern Developer Portfolio Interactions
   ========================================== */

// ==========================================
// Custom Cursor
// ==========================================
class CustomCursor {
    constructor() {
        this.cursor = document.querySelector('.cursor');
        this.follower = document.querySelector('.cursor-follower');
        this.links = document.querySelectorAll('a, button, .project-card, .service-card, .skill-category');
        
        this.cursorX = 0;
        this.cursorY = 0;
        this.followerX = 0;
        this.followerY = 0;
        
        this.init();
    }
    
    init() {
        if (!this.cursor || !this.follower) return;
        
        document.addEventListener('mousemove', (e) => {
            this.cursorX = e.clientX;
            this.cursorY = e.clientY;
        });
        
        this.links.forEach(link => {
            link.addEventListener('mouseenter', () => {
                this.follower.classList.add('hover');
            });
            
            link.addEventListener('mouseleave', () => {
                this.follower.classList.remove('hover');
            });
        });
        
        this.animate();
    }
    
    animate() {
        // Smooth cursor movement
        this.followerX += (this.cursorX - this.followerX) * 0.15;
        this.followerY += (this.cursorY - this.followerY) * 0.15;
        
        this.cursor.style.transform = `translate(${this.cursorX - 5}px, ${this.cursorY - 5}px)`;
        this.follower.style.transform = `translate(${this.followerX - 20}px, ${this.followerY - 20}px)`;
        
        requestAnimationFrame(() => this.animate());
    }
}

// ==========================================
// Header Scroll Effect
// ==========================================
class HeaderScroll {
    constructor() {
        this.header = document.querySelector('.header');
        this.lastScroll = 0;
        
        this.init();
    }
    
    init() {
        if (!this.header) return;
        
        window.addEventListener('scroll', () => {
            const currentScroll = window.pageYOffset;
            
            if (currentScroll > 50) {
                this.header.classList.add('scrolled');
            } else {
                this.header.classList.remove('scrolled');
            }
            
            this.lastScroll = currentScroll;
        });
    }
}

// ==========================================
// Mobile Navigation
// ==========================================
class MobileNav {
    constructor() {
        this.toggle = document.querySelector('.nav-toggle');
        this.menu = document.querySelector('.nav-menu');
        this.links = document.querySelectorAll('.nav-link');
        
        this.init();
    }
    
    init() {
        if (!this.toggle || !this.menu) return;
        
        this.toggle.addEventListener('click', () => {
            this.toggle.classList.toggle('active');
            this.menu.classList.toggle('active');
            document.body.style.overflow = this.menu.classList.contains('active') ? 'hidden' : '';
        });
        
        this.links.forEach(link => {
            link.addEventListener('click', () => {
                this.toggle.classList.remove('active');
                this.menu.classList.remove('active');
                document.body.style.overflow = '';
            });
        });
    }
}

// ==========================================
// Smooth Scroll
// ==========================================
class SmoothScroll {
    constructor() {
        this.links = document.querySelectorAll('a[href^="#"]');
        this.init();
    }
    
    init() {
        this.links.forEach(link => {
            link.addEventListener('click', (e) => {
                const href = link.getAttribute('href');
                if (href === '#') return;
                
                e.preventDefault();
                const target = document.querySelector(href);
                
                if (target) {
                    const headerOffset = 100;
                    const elementPosition = target.getBoundingClientRect().top;
                    const offsetPosition = elementPosition + window.pageYOffset - headerOffset;
                    
                    window.scrollTo({
                        top: offsetPosition,
                        behavior: 'smooth'
                    });
                }
            });
        });
    }
}

// ==========================================
// Animate On Scroll (AOS-like)
// ==========================================
class ScrollAnimations {
    constructor() {
        this.elements = document.querySelectorAll('[data-aos]');
        this.init();
    }
    
    init() {
        if (!this.elements.length) return;
        
        // Initial check
        this.checkElements();
        
        // Check on scroll with throttling
        let ticking = false;
        window.addEventListener('scroll', () => {
            if (!ticking) {
                window.requestAnimationFrame(() => {
                    this.checkElements();
                    ticking = false;
                });
                ticking = true;
            }
        });
    }
    
    checkElements() {
        this.elements.forEach(element => {
            const rect = element.getBoundingClientRect();
            const windowHeight = window.innerHeight;
            
            // Get delay from data attribute
            const delay = element.dataset.aosDelay || 0;
            
            if (rect.top < windowHeight * 0.85) {
                setTimeout(() => {
                    element.classList.add('aos-animate');
                }, parseInt(delay));
            }
        });
    }
}

// ==========================================
// Counter Animation
// ==========================================
class CounterAnimation {
    constructor() {
        this.counters = document.querySelectorAll('.stat-number[data-count]');
        this.animated = new Set();
        this.init();
    }
    
    init() {
        if (!this.counters.length) return;
        
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting && !this.animated.has(entry.target)) {
                    this.animateCounter(entry.target);
                    this.animated.add(entry.target);
                }
            });
        }, { threshold: 0.5 });
        
        this.counters.forEach(counter => observer.observe(counter));
    }
    
    animateCounter(element) {
        const target = parseInt(element.dataset.count);
        const duration = 2000;
        const start = 0;
        const startTime = performance.now();
        
        const easeOutQuart = (t) => 1 - Math.pow(1 - t, 4);
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            const value = Math.floor(easeOutQuart(progress) * (target - start) + start);
            element.textContent = value;
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                element.textContent = target;
            }
        };
        
        requestAnimationFrame(animate);
    }
}

// ==========================================
// Testimonials Carousel
// ==========================================
class TestimonialsCarousel {
    constructor() {
        this.track = document.querySelector('.testimonials-track');
        this.cards = document.querySelectorAll('.testimonial-card');
        this.prevBtn = document.querySelector('.carousel-btn--prev');
        this.nextBtn = document.querySelector('.carousel-btn--next');
        
        this.currentIndex = 0;
        this.isAnimating = false;
        
        this.init();
    }
    
    init() {
        if (!this.track || !this.cards.length) return;
        
        // Clone cards for infinite scroll effect
        this.cloneCards();
        
        // Button controls (optional manual control)
        if (this.prevBtn && this.nextBtn) {
            this.prevBtn.addEventListener('click', () => this.pause());
            this.nextBtn.addEventListener('click', () => this.play());
        }
    }
    
    cloneCards() {
        // Clone all cards and append for seamless loop
        this.cards.forEach(card => {
            const clone = card.cloneNode(true);
            this.track.appendChild(clone);
        });
    }
    
    pause() {
        if (this.track) {
            this.track.style.animationPlayState = 'paused';
        }
    }
    
    play() {
        if (this.track) {
            this.track.style.animationPlayState = 'running';
        }
    }
}

// ==========================================
// Parallax Effect
// ==========================================
class ParallaxEffect {
    constructor() {
        this.floatingImages = document.querySelectorAll('.floating-img');
        this.heroImage = document.querySelector('.hero-image');
        
        this.init();
    }
    
    init() {
        if (!this.floatingImages.length && !this.heroImage) return;
        
        window.addEventListener('mousemove', (e) => {
            const x = (e.clientX - window.innerWidth / 2) / 50;
            const y = (e.clientY - window.innerHeight / 2) / 50;
            
            this.floatingImages.forEach((img, index) => {
                const speed = (index + 1) * 0.5;
                img.style.transform = `translate(${x * speed}px, ${y * speed}px)`;
            });
        });
    }
}

// ==========================================
// Text Reveal Animation
// ==========================================
class TextReveal {
    constructor() {
        this.titles = document.querySelectorAll('.hero-title .title-line');
        this.init();
    }
    
    init() {
        if (!this.titles.length) return;
        
        this.titles.forEach((title, index) => {
            title.style.opacity = '0';
            title.style.transform = 'translateY(100%)';
            
            setTimeout(() => {
                title.style.transition = 'opacity 0.8s ease, transform 0.8s ease';
                title.style.opacity = '1';
                title.style.transform = 'translateY(0)';
            }, 300 + (index * 200));
        });
    }
}

// ==========================================
// Magnetic Button Effect
// ==========================================
class MagneticButtons {
    constructor() {
        this.buttons = document.querySelectorAll('.btn, .project-link, .carousel-btn');
        this.init();
    }
    
    init() {
        if (!this.buttons.length) return;
        
        this.buttons.forEach(button => {
            button.addEventListener('mousemove', (e) => {
                const rect = button.getBoundingClientRect();
                const x = e.clientX - rect.left - rect.width / 2;
                const y = e.clientY - rect.top - rect.height / 2;
                
                button.style.transform = `translate(${x * 0.2}px, ${y * 0.2}px)`;
            });
            
            button.addEventListener('mouseleave', () => {
                button.style.transform = 'translate(0, 0)';
            });
        });
    }
}

// ==========================================
// Typing Effect
// ==========================================
class TypingEffect {
    constructor(element, texts, speed = 100) {
        this.element = element;
        this.texts = texts;
        this.speed = speed;
        this.textIndex = 0;
        this.charIndex = 0;
        this.isDeleting = false;
        
        this.init();
    }
    
    init() {
        if (!this.element) return;
        this.type();
    }
    
    type() {
        const currentText = this.texts[this.textIndex];
        
        if (this.isDeleting) {
            this.element.textContent = currentText.substring(0, this.charIndex - 1);
            this.charIndex--;
        } else {
            this.element.textContent = currentText.substring(0, this.charIndex + 1);
            this.charIndex++;
        }
        
        let typeSpeed = this.speed;
        
        if (this.isDeleting) {
            typeSpeed /= 2;
        }
        
        if (!this.isDeleting && this.charIndex === currentText.length) {
            typeSpeed = 2000; // Pause at end
            this.isDeleting = true;
        } else if (this.isDeleting && this.charIndex === 0) {
            this.isDeleting = false;
            this.textIndex = (this.textIndex + 1) % this.texts.length;
            typeSpeed = 500;
        }
        
        setTimeout(() => this.type(), typeSpeed);
    }
}

// ==========================================
// Image Lazy Loading
// ==========================================
class LazyLoad {
    constructor() {
        this.images = document.querySelectorAll('img[data-src]');
        this.init();
    }
    
    init() {
        if (!this.images.length) return;
        
        if ('IntersectionObserver' in window) {
            const observer = new IntersectionObserver((entries) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        img.src = img.dataset.src;
                        img.removeAttribute('data-src');
                        observer.unobserve(img);
                    }
                });
            }, { rootMargin: '50px' });
            
            this.images.forEach(img => observer.observe(img));
        } else {
            // Fallback for older browsers
            this.images.forEach(img => {
                img.src = img.dataset.src;
            });
        }
    }
}

// ==========================================
// Form Validation (if contact form exists)
// ==========================================
class FormValidation {
    constructor(formSelector) {
        this.form = document.querySelector(formSelector);
        this.init();
    }
    
    init() {
        if (!this.form) return;
        
        this.form.addEventListener('submit', (e) => {
            e.preventDefault();
            
            const inputs = this.form.querySelectorAll('input, textarea');
            let isValid = true;
            
            inputs.forEach(input => {
                if (input.hasAttribute('required') && !input.value.trim()) {
                    isValid = false;
                    this.showError(input, 'Ce champ est requis');
                } else if (input.type === 'email' && !this.isValidEmail(input.value)) {
                    isValid = false;
                    this.showError(input, 'Email invalide');
                } else {
                    this.clearError(input);
                }
            });
            
            if (isValid) {
                this.submitForm();
            }
        });
    }
    
    isValidEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }
    
    showError(input, message) {
        input.style.borderColor = '#ff4444';
        const errorEl = input.nextElementSibling;
        if (errorEl && errorEl.classList.contains('error-message')) {
            errorEl.textContent = message;
        }
    }
    
    clearError(input) {
        input.style.borderColor = '';
        const errorEl = input.nextElementSibling;
        if (errorEl && errorEl.classList.contains('error-message')) {
            errorEl.textContent = '';
        }
    }
    
    submitForm() {
        // Add your form submission logic here
        console.log('Form submitted!');
    }
}

// ==========================================
// Dark/Light Theme Toggle (Optional)
// ==========================================
class ThemeToggle {
    constructor() {
        this.toggle = document.querySelector('.theme-toggle');
        this.body = document.body;
        this.init();
    }
    
    init() {
        if (!this.toggle) return;
        
        // Check for saved theme preference
        const savedTheme = localStorage.getItem('theme');
        if (savedTheme) {
            this.body.setAttribute('data-theme', savedTheme);
        }
        
        this.toggle.addEventListener('click', () => {
            const currentTheme = this.body.getAttribute('data-theme');
            const newTheme = currentTheme === 'light' ? 'dark' : 'light';
            
            this.body.setAttribute('data-theme', newTheme);
            localStorage.setItem('theme', newTheme);
        });
    }
}

// ==========================================
// Scroll Progress Indicator
// ==========================================
class ScrollProgress {
    constructor() {
        this.createProgressBar();
        this.init();
    }
    
    createProgressBar() {
        const progressBar = document.createElement('div');
        progressBar.className = 'scroll-progress';
        progressBar.innerHTML = '<div class="scroll-progress-bar"></div>';
        document.body.appendChild(progressBar);
        
        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            .scroll-progress {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 3px;
                background: transparent;
                z-index: 10001;
            }
            .scroll-progress-bar {
                height: 100%;
                background: var(--color-primary, #00ff88);
                width: 0%;
                transition: width 0.1s ease;
            }
        `;
        document.head.appendChild(style);
        
        this.progressBar = progressBar.querySelector('.scroll-progress-bar');
    }
    
    init() {
        window.addEventListener('scroll', () => {
            const windowHeight = document.documentElement.scrollHeight - window.innerHeight;
            const progress = (window.pageYOffset / windowHeight) * 100;
            this.progressBar.style.width = `${progress}%`;
        });
    }
}

// ==========================================
// Preloader
// ==========================================
class Preloader {
    constructor() {
        this.createPreloader();
        this.init();
    }
    
    createPreloader() {
        const preloader = document.createElement('div');
        preloader.className = 'preloader';
        preloader.innerHTML = `
            <div class="preloader-content">
                <div class="preloader-logo">&lt;/&gt;</div>
                <div class="preloader-text">Loading...</div>
            </div>
        `;
        document.body.appendChild(preloader);
        
        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            .preloader {
                position: fixed;
                inset: 0;
                background: var(--color-bg, #0a0a0a);
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 100000;
                transition: opacity 0.5s ease, visibility 0.5s ease;
            }
            .preloader.hidden {
                opacity: 0;
                visibility: hidden;
            }
            .preloader-content {
                text-align: center;
            }
            .preloader-logo {
                font-family: var(--font-mono, monospace);
                font-size: 3rem;
                color: var(--color-primary, #00ff88);
                animation: pulse 1s ease-in-out infinite;
            }
            .preloader-text {
                margin-top: 1rem;
                color: var(--color-text-muted, #666);
                font-size: 0.875rem;
                letter-spacing: 2px;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; transform: scale(1); }
                50% { opacity: 0.5; transform: scale(0.95); }
            }
        `;
        document.head.appendChild(style);
        
        this.preloader = preloader;
    }
    
    init() {
        window.addEventListener('load', () => {
            setTimeout(() => {
                this.preloader.classList.add('hidden');
                setTimeout(() => {
                    this.preloader.remove();
                }, 500);
            }, 500);
        });
    }
}

// ==========================================
// Initialize Everything
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    // Core functionality
    new CustomCursor();
    new HeaderScroll();
    new MobileNav();
    new SmoothScroll();
    new ScrollAnimations();
    new CounterAnimation();
    new TestimonialsCarousel();
    
    // Visual enhancements
    new ParallaxEffect();
    new TextReveal();
    new MagneticButtons();
    new LazyLoad();
    new ScrollProgress();
    new Preloader();
    
    // Optional features
    // new TypingEffect(document.querySelector('.typing-text'), ['Developer', 'Designer', 'Creator']);
    // new ThemeToggle();
    // new FormValidation('#contact-form');

});

// ==========================================
// Utility Functions
// ==========================================

// Debounce function for performance
function debounce(func, wait = 20, immediate = true) {
    let timeout;
    return function() {
        const context = this, args = arguments;
        const later = function() {
            timeout = null;
            if (!immediate) func.apply(context, args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func.apply(context, args);
    };
}

// Throttle function for scroll events
function throttle(func, limit) {
    let inThrottle;
    return function() {
        const args = arguments;
        const context = this;
        if (!inThrottle) {
            func.apply(context, args);
            inThrottle = true;
            setTimeout(() => inThrottle = false, limit);
        }
    };
}

// Get random number in range
function randomInRange(min, max) {
    return Math.random() * (max - min) + min;
}

// Lerp (Linear interpolation)
function lerp(start, end, amt) {
    return (1 - amt) * start + amt * end;
}
