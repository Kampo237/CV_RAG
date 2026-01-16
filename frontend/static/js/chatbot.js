/* ==========================================
   CHATBOT WIDGET - JAVASCRIPT
   Version 2.0 - Compatible avec l'API RAG
   ========================================== */

(function() {
    'use strict';

    console.log('[Chatbot] Script chargé v2.0');

    // ==========================================
    // Configuration
    // ==========================================
    var CONFIG = {
        // Les endpoints passent par le proxy Django (même domaine = pas de CORS)
        API_BASE_URL: '',
        ENDPOINTS: {
            AUTH: '/api/chat/session',
            CHAT: '/api/chat/message'
        },
        SESSION_KEY: 'jp_chat_session',
        SESSION_EXPIRY_DAYS: 30,
        DEFAULT_QUOTA: 50,
        MIN_TIME_BETWEEN_MESSAGES: 1500,
        MIN_MESSAGE_LENGTH: 2,
        MAX_MESSAGE_LENGTH: 500,
        WELCOME_MESSAGE: "Bonjour ! Je suis l'assistant virtuel de Jordan. Je peux vous renseigner sur son parcours, ses compétences techniques et ses projets. Comment puis-je vous aider ?"
    };

    // ==========================================
    // Utilitaires
    // ==========================================
    function log(msg) {
        console.log('[Chatbot] ' + msg);
    }

    function logError(msg) {
        console.error('[Chatbot ERROR] ' + msg);
    }

    function escapeHtml(text) {
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    function formatMessage(content) {
        // Retirer les métadonnées si présentes
        if (content.indexOf('__METADATA__') !== -1) {
            content = content.split('__METADATA__')[0];
        }

        return content
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/`(.*?)`/g, '<code>$1</code>')
            .replace(/\n/g, '<br>');
    }

    function validateEmail(email) {
        return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    }

    function getTime() {
        var now = new Date();
        var h = now.getHours().toString().padStart(2, '0');
        var m = now.getMinutes().toString().padStart(2, '0');
        return h + ':' + m;
    }

    // ==========================================
    // Session Storage
    // ==========================================
    var Session = {
        data: null,
        lastMessageTime: 0,

        get: function() {
            try {
                var stored = localStorage.getItem(CONFIG.SESSION_KEY);
                if (!stored) return null;
                var session = JSON.parse(stored);
                if (session.expiresAt && Date.now() > session.expiresAt) {
                    this.clear();
                    return null;
                }
                this.data = session;
                return session;
            } catch (e) {
                this.clear();
                return null;
            }
        },

        set: function(sessionData) {
            sessionData.expiresAt = Date.now() + (CONFIG.SESSION_EXPIRY_DAYS * 24 * 60 * 60 * 1000);
            localStorage.setItem(CONFIG.SESSION_KEY, JSON.stringify(sessionData));
            this.data = sessionData;
            return sessionData;
        },

        clear: function() {
            localStorage.removeItem(CONFIG.SESSION_KEY);
            this.data = null;
        },

        canSendMessage: function() {
            var now = Date.now();
            var timeSince = now - this.lastMessageTime;

            if (timeSince < CONFIG.MIN_TIME_BETWEEN_MESSAGES) {
                var wait = Math.ceil((CONFIG.MIN_TIME_BETWEEN_MESSAGES - timeSince) / 1000);
                return { allowed: false, reason: 'Attendez ' + wait + 's' };
            }

            if (this.data && this.data.quotaRemaining <= 0) {
                return { allowed: false, reason: 'Quota épuisé' };
            }

            return { allowed: true };
        },

        recordMessage: function() {
            this.lastMessageTime = Date.now();
            if (this.data) {
                this.data.quotaRemaining = Math.max(0, this.data.quotaRemaining - 1);
                this.set(this.data);
            }
        }
    };

    // ==========================================
    // Fallback Responses
    // ==========================================
    function getFallbackResponse(message) {
        var msg = message.toLowerCase();

        if (msg.indexOf('bonjour') !== -1 || msg.indexOf('salut') !== -1 || msg.indexOf('hello') !== -1) {
            return "Bonjour ! Je suis l'assistant de Jordan. Comment puis-je vous aider ?";
        }
        if (msg.indexOf('compétence') !== -1 || msg.indexOf('skill') !== -1 || msg.indexOf('technologie') !== -1) {
            return "Jordan maîtrise C# .NET 8, Python (Django/FastAPI), les systèmes RAG avec LangChain, Docker, AWS, et PostgreSQL. Il a aussi de l'expérience avec WPF et Unity.";
        }
        if (msg.indexOf('projet') !== -1 || msg.indexOf('portfolio') !== -1) {
            return "Jordan a réalisé plusieurs projets :\n\n• CV Chatbot RAG - Chatbot intelligent avec architecture RAG\n• NOVA GAMES S2J - Plateforme e-commerce Django\n• Gestionnaire de dépenses - Application WPF";
        }
        if (msg.indexOf('étude') !== -1 || msg.indexOf('formation') !== -1 || msg.indexOf('cégep') !== -1) {
            return "Jordan est étudiant finissant en informatique au Cégep de Chicoutimi. Il a reçu une mention honorable au Hackathon UQAC 2025.";
        }
        if (msg.indexOf('contact') !== -1 || msg.indexOf('email') !== -1 || msg.indexOf('stage') !== -1) {
            return "Vous pouvez contacter Jordan à kampojordan237@gmail.com. Il est actuellement à la recherche d'un stage ou d'une première opportunité professionnelle.";
        }
        return "Je suis l'assistant de Jordan. Je peux vous renseigner sur son parcours, ses compétences et ses projets. Que souhaitez-vous savoir ?";
    }

    // ==========================================
    // Chatbot Class
    // ==========================================
    function ChatbotWidget() {
        this.isOpen = false;
        this.isTyping = false;
        this.elements = {};
        this.currentStreamContent = '';
    }

    ChatbotWidget.prototype.init = function() {
        log('Initialisation...');

        this.elements = {
            widget: document.getElementById('chatbot-widget'),
            toggle: document.getElementById('chatbot-toggle'),
            badge: document.getElementById('chatbot-badge'),
            window: document.getElementById('chatbot-window'),
            authScreen: document.getElementById('chatbot-auth'),
            authForm: document.getElementById('chatbot-auth-form'),
            authEmail: document.getElementById('chatbot-auth-email'),
            authError: document.getElementById('chatbot-auth-error'),
            authSubmit: document.getElementById('chatbot-auth-submit'),
            messages: document.getElementById('chatbot-messages'),
            inputArea: document.getElementById('chatbot-input-area'),
            inputForm: document.getElementById('chatbot-input-form'),
            textarea: document.getElementById('chatbot-textarea'),
            sendBtn: document.getElementById('chatbot-send-btn'),
            charCount: document.getElementById('chatbot-char-count'),
            warning: document.getElementById('chatbot-warning'),
            typing: document.getElementById('chatbot-typing'),
            minimizeBtn: document.getElementById('chatbot-minimize-btn'),
            resizeBtn: document.getElementById('chatbot-resize-btn'),
        };

        if (!this.elements.widget) {
            logError('Element chatbot-widget introuvable');
            return false;
        }
        if (!this.elements.toggle) {
            logError('Element chatbot-toggle introuvable');
            return false;
        }

        log('Éléments trouvés, attachement des événements...');
        this.bindEvents();
        this.checkSession();
        log('Initialisation terminée avec succès');
        return true;
    };

    ChatbotWidget.prototype.bindEvents = function() {
        var self = this;

        if (this.elements.toggle) {
            this.elements.toggle.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                self.toggleWindow();
            });
        }

        if (this.elements.minimizeBtn) {
            this.elements.minimizeBtn.addEventListener('click', function(e) {
                e.preventDefault();
                self.toggleWindow();
            });
        }

        if (this.elements.resizeBtn) {
            this.elements.resizeBtn.addEventListener('click', function(e) {
                e.preventDefault();
                self.toggleSize();
            });
        }

        if (this.elements.authForm) {
            this.elements.authForm.addEventListener('submit', function(e) {
                e.preventDefault();
                self.handleAuth();
            });
        }

        if (this.elements.authEmail) {
            this.elements.authEmail.addEventListener('input', function() {
                self.clearAuthError();
            });
        }

        if (this.elements.inputForm) {
            this.elements.inputForm.addEventListener('submit', function(e) {
                e.preventDefault();
                self.handleSend();
            });
        }

        if (this.elements.textarea) {
            this.elements.textarea.addEventListener('input', function() {
                self.handleTextareaChange();
            });
            this.elements.textarea.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    self.handleSend();
                }
            });
        }

        log('Événements attachés');
    };

    ChatbotWidget.prototype.toggleWindow = function() {
        this.isOpen = !this.isOpen;
        log('Toggle window: ' + (this.isOpen ? 'ouvert' : 'fermé'));

        if (this.elements.toggle) {
            this.elements.toggle.classList.toggle('active', this.isOpen);
        }
        if (this.elements.window) {
            this.elements.window.classList.toggle('open', this.isOpen);
        }
        if (this.isOpen && this.elements.badge) {
            this.elements.badge.classList.add('hidden');
        }

        var self = this;
        if (this.isOpen) {
            setTimeout(function() {
                if (self.elements.authScreen && !self.elements.authScreen.classList.contains('hidden')) {
                    if (self.elements.authEmail) self.elements.authEmail.focus();
                } else {
                    if (self.elements.textarea) self.elements.textarea.focus();
                }
            }, 300);
        }
    };

    ChatbotWidget.prototype.toggleSize = function() {
        var isExpanded = this.elements.window.classList.toggle('expanded');

        if (this.elements.resizeBtn) {
            this.elements.resizeBtn.classList.toggle('expanded', isExpanded);
            this.elements.resizeBtn.title = isExpanded ? 'Réduire' : 'Agrandir';
        }

        log('Toggle size: ' + (isExpanded ? 'agrandi' : 'normal'));
        this.scrollToBottom();
    };

    ChatbotWidget.prototype.checkSession = function() {
        var session = Session.get();

        if (session && session.id) {
            log('Session existante trouvée: ' + session.id);
            this.showChatInterface();

            if (session.messages && session.messages.length > 0) {
                this.loadHistory(session.messages);
            } else {
                this.addBotMessage(CONFIG.WELCOME_MESSAGE);
            }
            this.updateQuotaDisplay();
        } else {
            log('Pas de session, affichage auth');
            this.showAuthScreen();
        }
    };

    ChatbotWidget.prototype.showAuthScreen = function() {
        if (this.elements.authScreen) this.elements.authScreen.classList.remove('hidden');
        if (this.elements.messages) this.elements.messages.classList.add('hidden');
        if (this.elements.inputArea) this.elements.inputArea.classList.add('hidden');
    };

    ChatbotWidget.prototype.showChatInterface = function() {
        if (this.elements.authScreen) this.elements.authScreen.classList.add('hidden');
        if (this.elements.messages) this.elements.messages.classList.remove('hidden');
        if (this.elements.inputArea) this.elements.inputArea.classList.remove('hidden');
    };

    ChatbotWidget.prototype.handleAuth = function() {
        var self = this;
        var email = this.elements.authEmail ? this.elements.authEmail.value.trim() : '';

        if (!validateEmail(email)) {
            this.showAuthError('Veuillez entrer un email valide');
            return;
        }

        log('Authentification: ' + email);

        if (this.elements.authSubmit) {
            this.elements.authSubmit.disabled = true;
            this.elements.authSubmit.innerHTML = '<span class="chatbot-spinner"></span>';
        }

        this.authenticateAPI(email)
            .then(function(session) {
                self.showChatInterface();
                if (session.messages && session.messages.length > 0) {
                    self.loadHistory(session.messages);
                } else {
                    self.addBotMessage(CONFIG.WELCOME_MESSAGE);
                }
                self.updateQuotaDisplay();
                if (self.elements.textarea) self.elements.textarea.focus();
            })
            .catch(function(error) {
                log('Auth API échouée, création session locale');
                var localSession = Session.set({
                    id: 'local_' + Date.now(),
                    email: email,
                    quotaRemaining: CONFIG.DEFAULT_QUOTA,
                    quotaTotal: CONFIG.DEFAULT_QUOTA,
                    messages: [],
                    isLocal: true
                });
                self.showChatInterface();
                self.addBotMessage(CONFIG.WELCOME_MESSAGE);
                self.updateQuotaDisplay();
                if (self.elements.textarea) self.elements.textarea.focus();
            })
            .finally(function() {
                if (self.elements.authSubmit) {
                    self.elements.authSubmit.disabled = false;
                    self.elements.authSubmit.innerHTML = '<span>Commencer</span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 12h14M12 5l7 7-7 7"/></svg>';
                }
            });
    };

    ChatbotWidget.prototype.authenticateAPI = function(email) {
        return fetch(CONFIG.API_BASE_URL + CONFIG.ENDPOINTS.AUTH, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email: email })
        })
        .then(function(response) {
            if (!response.ok) throw new Error('Auth failed');
            return response.json();
        })
        .then(function(data) {
            return Session.set({
                id: data.session_id,
                email: data.email,
                quotaRemaining: data.quota_remaining || CONFIG.DEFAULT_QUOTA,
                quotaTotal: data.quota_total || CONFIG.DEFAULT_QUOTA,
                messages: data.messages || []
            });
        });
    };

    ChatbotWidget.prototype.showAuthError = function(msg) {
        if (this.elements.authError) {
            this.elements.authError.textContent = msg;
            this.elements.authError.classList.add('visible');
        }
        if (this.elements.authEmail) {
            this.elements.authEmail.classList.add('error');
        }
    };

    ChatbotWidget.prototype.clearAuthError = function() {
        if (this.elements.authError) {
            this.elements.authError.classList.remove('visible');
        }
        if (this.elements.authEmail) {
            this.elements.authEmail.classList.remove('error');
        }
    };

    ChatbotWidget.prototype.loadHistory = function(messages) {
        if (!this.elements.messages) return;
        this.elements.messages.innerHTML = '';

        for (var i = 0; i < messages.length; i++) {
            var msg = messages[i];
            if (msg.role === 'assistant') {
                this.addBotMessage(msg.content, false);
            } else {
                this.addUserMessage(msg.content, false);
            }
        }
        this.scrollToBottom();
    };

    ChatbotWidget.prototype.handleTextareaChange = function() {
        if (!this.elements.textarea) return;

        var value = this.elements.textarea.value;
        var length = value.length;

        this.elements.textarea.style.height = 'auto';
        this.elements.textarea.style.height = Math.min(this.elements.textarea.scrollHeight, 120) + 'px';

        if (this.elements.charCount) {
            this.elements.charCount.textContent = length + '/' + CONFIG.MAX_MESSAGE_LENGTH;
            this.elements.charCount.classList.remove('warning', 'error');
            if (length > CONFIG.MAX_MESSAGE_LENGTH * 0.9) {
                this.elements.charCount.classList.add('error');
            } else if (length > CONFIG.MAX_MESSAGE_LENGTH * 0.75) {
                this.elements.charCount.classList.add('warning');
            }
        }

        if (this.elements.sendBtn) {
            this.elements.sendBtn.disabled = length < CONFIG.MIN_MESSAGE_LENGTH || this.isTyping;
        }
    };

    ChatbotWidget.prototype.handleSend = function() {
        if (this.isTyping) return;

        var message = this.elements.textarea ? this.elements.textarea.value.trim() : '';

        if (message.length < CONFIG.MIN_MESSAGE_LENGTH) {
            this.showWarning('Message trop court');
            return;
        }
        if (message.length > CONFIG.MAX_MESSAGE_LENGTH) {
            this.showWarning('Message trop long');
            return;
        }

        var canSend = Session.canSendMessage();
        if (!canSend.allowed) {
            this.showWarning(canSend.reason);
            return;
        }

        log('Envoi message: ' + message);

        if (this.elements.textarea) {
            this.elements.textarea.value = '';
            this.handleTextareaChange();
        }

        this.addUserMessage(message);
        Session.recordMessage();
        this.updateQuotaDisplay();
        this.sendToAPI(message);
    };

    ChatbotWidget.prototype.sendToAPI = function(message) {
        var self = this;
        var session = Session.get();

        this.showTyping(true);

        fetch(CONFIG.API_BASE_URL + CONFIG.ENDPOINTS.CHAT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                message: message,
                session_id: session ? session.id : 'anonymous'
            })
        })
        .then(function(response) {
            if (!response.ok) throw new Error('API error');

            // Handle streaming response
            return self.handleStreamingResponse(response);
        })
        .catch(function(error) {
            log('API error, using fallback: ' + error);
            self.showTyping(false);
            var fallback = getFallbackResponse(message);
            self.addBotMessage(fallback);
        });
    };

    ChatbotWidget.prototype.handleStreamingResponse = function(response) {
        var self = this;
        var reader = response.body.getReader();
        var decoder = new TextDecoder();
        var fullResponse = '';

        this.showTyping(false);
        var msgEl = this.createBotMessageElement();
        var contentEl = msgEl.querySelector('.chatbot-message-content');

        function read() {
            reader.read().then(function(result) {
                if (result.done) {
                    // Nettoyer les métadonnées de l'affichage final
                    var cleanResponse = fullResponse.split('__METADATA__')[0];
                    contentEl.innerHTML = formatMessage(cleanResponse);
                    self.scrollToBottom();
                    return;
                }

                var chunk = decoder.decode(result.value, { stream: true });
                fullResponse += chunk;

                // Afficher seulement le contenu sans les métadonnées
                var displayContent = fullResponse.split('__METADATA__')[0];
                contentEl.innerHTML = formatMessage(displayContent);
                self.scrollToBottom();

                read();
            }).catch(function(error) {
                logError('Stream error: ' + error);
            });
        }

        read();
    };

    ChatbotWidget.prototype.addUserMessage = function(content, animate) {
        if (animate === undefined) animate = true;
        if (!this.elements.messages) return;

        var session = Session.get();
        var initial = (session && session.email) ? session.email[0].toUpperCase() : 'U';

        var div = document.createElement('div');
        div.className = 'chatbot-message user';
        if (!animate) div.style.animation = 'none';

        div.innerHTML =
            '<div class="chatbot-message-avatar">' + initial + '</div>' +
            '<div class="chatbot-message-wrapper">' +
                '<div class="chatbot-message-content">' + escapeHtml(content) + '</div>' +
                '<div class="chatbot-message-time">' + getTime() + '</div>' +
            '</div>';

        this.elements.messages.appendChild(div);
        this.scrollToBottom();
    };

    ChatbotWidget.prototype.addBotMessage = function(content, animate) {
        if (animate === undefined) animate = true;
        if (!this.elements.messages) return;

        var div = document.createElement('div');
        div.className = 'chatbot-message bot';
        if (!animate) div.style.animation = 'none';

        div.innerHTML =
            '<div class="chatbot-message-avatar">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                    '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' +
                '</svg>' +
            '</div>' +
            '<div class="chatbot-message-wrapper">' +
                '<div class="chatbot-message-content">' + formatMessage(content) + '</div>' +
                '<div class="chatbot-message-time">' + getTime() + '</div>' +
            '</div>';

        this.elements.messages.appendChild(div);
        this.scrollToBottom();
    };

    ChatbotWidget.prototype.createBotMessageElement = function() {
        if (!this.elements.messages) return null;

        var div = document.createElement('div');
        div.className = 'chatbot-message bot';

        div.innerHTML =
            '<div class="chatbot-message-avatar">' +
                '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">' +
                    '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>' +
                '</svg>' +
            '</div>' +
            '<div class="chatbot-message-wrapper">' +
                '<div class="chatbot-message-content"></div>' +
                '<div class="chatbot-message-time">' + getTime() + '</div>' +
            '</div>';

        this.elements.messages.appendChild(div);
        return div;
    };

    ChatbotWidget.prototype.showTyping = function(show) {
        if (this.elements.typing) {
            this.elements.typing.classList.toggle('visible', show);
        }
        this.isTyping = show;
        if (show && this.elements.sendBtn) {
            this.elements.sendBtn.disabled = true;
        }
        if (show) this.scrollToBottom();
    };

    ChatbotWidget.prototype.showWarning = function(msg) {
        var self = this;
        if (this.elements.warning) {
            this.elements.warning.textContent = msg;
            this.elements.warning.classList.add('visible');
            setTimeout(function() {
                self.elements.warning.classList.remove('visible');
            }, 4000);
        }
    };

    ChatbotWidget.prototype.updateQuotaDisplay = function() {
        var session = Session.get();
        if (this.elements.quotaCount && session) {
            var remaining = session.quotaRemaining || 0;
            var total = session.quotaTotal || CONFIG.DEFAULT_QUOTA;
            var pct = Math.round((remaining / total) * 100);

            this.elements.quotaCount.textContent = remaining + ' questions restantes';
            this.elements.quotaCount.classList.remove('low', 'critical');

            if (pct <= 10) {
                this.elements.quotaCount.classList.add('critical');
            } else if (pct <= 30) {
                this.elements.quotaCount.classList.add('low');
            }
        }
    };

    ChatbotWidget.prototype.scrollToBottom = function() {
        var self = this;
        if (this.elements.messages) {
            requestAnimationFrame(function() {
                self.elements.messages.scrollTop = self.elements.messages.scrollHeight;
            });
        }
    };

    // ==========================================
    // Initialisation
    // ==========================================
    function initChatbot() {
        log('Début initialisation...');

        var widget = document.getElementById('chatbot-widget');
        if (!widget) {
            logError('Widget introuvable dans le DOM');
            return;
        }

        var chatbot = new ChatbotWidget();
        if (chatbot.init()) {
            window.chatbot = chatbot;
            log('Chatbot prêt! (window.chatbot disponible)');
        } else {
            logError('Échec initialisation');
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initChatbot);
    } else {
        initChatbot();
    }

    window.addEventListener('load', function() {
        if (!window.chatbot) {
            log('Retry sur window.load...');
            initChatbot();
        }
    });

})();
