/* ==========================================
   CHATBOT ACTION INTERCEPTOR
   Intercepte les réponses du chatbot pour
   exécuter des actions dynamiques sur la page
   ========================================== */

(function() {
    'use strict';

    console.log('[ActionInterceptor] Module chargé');

    // ==========================================
    // Configuration
    // ==========================================
    var CONFIG = {
        // Délai avant redirection (ms) pour laisser le temps de lire
        REDIRECT_DELAY: 1500,

        // Délai pour scroll smooth
        SCROLL_DELAY: 300,

        // Durée d'affichage des notifications (ms)
        NOTIFICATION_DURATION: 5000,

        // Activer les logs de debug
        DEBUG: true,

        // URLs des pages du site
        ROUTES: {
            home: '/',
            about: '/about',
            projects: '/projects',
            cv: '/cv',
            contact: '/cv#contact',
            testimonial: '/testimonial',
            skills: '/#skills',
            services: '/#services'
        },

        // Liens externes
        EXTERNAL_LINKS: {
            github: 'https://github.com/Kampo237',
            linkedin: 'https://www.linkedin.com/in/yann-willy-jordan-pokam-teguia-a1b77b363',
            email: 'mailto:kampojordan237@gmail.com'
        }
    };

    // ==========================================
    // Logger
    // ==========================================
    function log(msg, data) {
        if (CONFIG.DEBUG) {
            if (data) {
                console.log('[ActionInterceptor] ' + msg, data);
            } else {
                console.log('[ActionInterceptor] ' + msg);
            }
        }
    }

    // ==========================================
    // Action Types Registry
    // ==========================================
    var ActionTypes = {
        REDIRECT: 'redirect',
        SCROLL_TO: 'scroll_to',
        SHOW_MODAL: 'show_modal',
        SHOW_PROJECT: 'show_project',
        SHOW_SKILL: 'show_skill',
        HIGHLIGHT: 'highlight',
        DOWNLOAD: 'download',
        OPEN_LINK: 'open_link',
        SHOW_CONTACT: 'show_contact',
        SHOW_NOTIFICATION: 'show_notification',
        TOGGLE_ELEMENT: 'toggle_element',
        PLAY_ANIMATION: 'play_animation',
        COPY_TO_CLIPBOARD: 'copy_clipboard',
        OPEN_TESTIMONIAL: 'open_testimonial'
    };

    // ==========================================
    // Intent Patterns (pour détecter l'intention dans le texte)
    // ==========================================
    var IntentPatterns = [
        // Navigation
        {
            patterns: [/voir (les |mes )?projets/i, /portfolio/i, /mes réalisations/i, /travaux/i],
            action: { type: ActionTypes.REDIRECT, target: 'projects' }
        },
        {
            patterns: [/page (d')?accueil/i, /retour.*(accueil|home)/i],
            action: { type: ActionTypes.REDIRECT, target: 'home' }
        },
        {
            patterns: [/à propos/i, /qui (est|suis)/i, /présentation/i, /parcours/i],
            action: { type: ActionTypes.REDIRECT, target: 'about' }
        },
        {
            patterns: [/voir (le |mon )?cv/i, /curriculum/i, /télécharger.*(cv|curriculum)/i],
            action: { type: ActionTypes.REDIRECT, target: 'cv' }
        },
        {
            patterns: [/laisser.*(commentaire|témoignage|avis)/i, /soumettre.*(témoignage|avis)/i],
            action: { type: ActionTypes.REDIRECT, target: 'testimonial' }
        },

        // Sections
        {
            patterns: [/voir (les |mes )?compétences/i, /skills/i, /technologies/i],
            action: { type: ActionTypes.SCROLL_TO, target: '#skills' }
        },
        {
            patterns: [/voir (les |mes )?services/i, /ce que (je propose|j'offre)/i],
            action: { type: ActionTypes.SCROLL_TO, target: '#services' }
        },

        // Contact
        {
            patterns: [/me contacter/i, /formulaire.*(contact)/i, /envoyer.*(message|email)/i],
            action: { type: ActionTypes.SHOW_CONTACT }
        },
        {
            patterns: [/email|courriel|adresse mail/i],
            action: { type: ActionTypes.COPY_TO_CLIPBOARD, data: 'kampojordan237@gmail.com', message: 'Email copié!' }
        },

        // Liens externes
        {
            patterns: [/github/i, /voir.*(code|repo)/i],
            action: { type: ActionTypes.OPEN_LINK, target: 'github' }
        },
        {
            patterns: [/linkedin/i, /profil professionnel/i],
            action: { type: ActionTypes.OPEN_LINK, target: 'linkedin' }
        },

        // Projets spécifiques
        {
            patterns: [/projet.*(chatbot|rag|cv chatbot)/i, /assistant.*(ia|intelligent)/i],
            action: { type: ActionTypes.SHOW_PROJECT, projectId: 'cv-chatbot' }
        },
        {
            patterns: [/projet.*(nova|games|e-commerce|ecommerce)/i],
            action: { type: ActionTypes.SHOW_PROJECT, projectId: 'nova-games' }
        },
        {
            patterns: [/projet.*(rpg|unity|companion|mobile)/i],
            action: { type: ActionTypes.SHOW_PROJECT, projectId: 'rpg-companion' }
        }
    ];

    // ==========================================
    // Action Executor
    // ==========================================
    var ActionExecutor = {

        // Exécuter une action
        execute: function(action) {
            log('Exécution action:', action);

            switch (action.type) {
                case ActionTypes.REDIRECT:
                    this.handleRedirect(action);
                    break;
                case ActionTypes.SCROLL_TO:
                    this.handleScrollTo(action);
                    break;
                case ActionTypes.SHOW_MODAL:
                    this.handleShowModal(action);
                    break;
                case ActionTypes.SHOW_PROJECT:
                    this.handleShowProject(action);
                    break;
                case ActionTypes.SHOW_SKILL:
                    this.handleShowSkill(action);
                    break;
                case ActionTypes.HIGHLIGHT:
                    this.handleHighlight(action);
                    break;
                case ActionTypes.DOWNLOAD:
                    this.handleDownload(action);
                    break;
                case ActionTypes.OPEN_LINK:
                    this.handleOpenLink(action);
                    break;
                case ActionTypes.SHOW_CONTACT:
                    this.handleShowContact(action);
                    break;
                case ActionTypes.SHOW_NOTIFICATION:
                    this.handleShowNotification(action);
                    break;
                case ActionTypes.TOGGLE_ELEMENT:
                    this.handleToggleElement(action);
                    break;
                case ActionTypes.PLAY_ANIMATION:
                    this.handlePlayAnimation(action);
                    break;
                case ActionTypes.COPY_TO_CLIPBOARD:
                    this.handleCopyToClipboard(action);
                    break;
                case ActionTypes.OPEN_TESTIMONIAL:
                    this.handleOpenTestimonial(action);
                    break;
                default:
                    log('Action non reconnue:', action.type);
            }
        },

        // Redirection vers une page
        handleRedirect: function(action) {
            var url = action.url || CONFIG.ROUTES[action.target] || action.target;

            if (!url) {
                log('URL de redirection non trouvée');
                return;
            }

            // Notification avant redirection
            this.showActionNotification('Redirection vers ' + (action.label || url) + '...', 'redirect');

            setTimeout(function() {
                if (url.startsWith('http')) {
                    window.open(url, '_blank');
                } else {
                    window.location.href = url;
                }
            }, CONFIG.REDIRECT_DELAY);
        },

        // Scroll vers un élément
        handleScrollTo: function(action) {
            var target = action.target || action.selector;
            var element = document.querySelector(target);

            if (!element) {
                // Si l'élément n'existe pas sur cette page, rediriger
                if (target.includes('#')) {
                    var page = target.split('#')[0] || '/';
                    window.location.href = page + target;
                }
                return;
            }

            // Fermer le chatbot si ouvert
            this.closeChatbot();

            setTimeout(function() {
                element.scrollIntoView({ behavior: 'smooth', block: 'start' });

                // Highlight temporaire
                element.classList.add('action-highlight');
                setTimeout(function() {
                    element.classList.remove('action-highlight');
                }, 2000);
            }, CONFIG.SCROLL_DELAY);
        },

        // Afficher un modal
        handleShowModal: function(action) {
            var modalId = action.modalId || action.target;
            var modal = document.getElementById(modalId);

            if (modal) {
                modal.classList.add('active', 'open');
                document.body.classList.add('modal-open');
            } else {
                // Créer un modal dynamique
                this.createDynamicModal(action);
            }
        },

        // Afficher un projet spécifique
        handleShowProject: function(action) {
            var projectId = action.projectId;
            var projectCard = document.querySelector('[data-project="' + projectId + '"]') ||
                              document.getElementById('project-' + projectId);

            if (projectCard) {
                // Scroll vers le projet
                this.closeChatbot();

                setTimeout(function() {
                    projectCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    projectCard.classList.add('action-highlight', 'project-spotlight');

                    setTimeout(function() {
                        projectCard.classList.remove('action-highlight', 'project-spotlight');
                    }, 3000);
                }, CONFIG.SCROLL_DELAY);
            } else {
                // Rediriger vers la page projets avec le projet en paramètre
                window.location.href = CONFIG.ROUTES.projects + '?highlight=' + projectId;
            }
        },

        // Afficher une compétence
        handleShowSkill: function(action) {
            var skillId = action.skillId || action.target;
            var skillElement = document.querySelector('[data-skill="' + skillId + '"]');

            if (skillElement) {
                this.closeChatbot();

                setTimeout(function() {
                    skillElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    skillElement.classList.add('action-highlight', 'skill-spotlight');

                    setTimeout(function() {
                        skillElement.classList.remove('action-highlight', 'skill-spotlight');
                    }, 2500);
                }, CONFIG.SCROLL_DELAY);
            }
        },

        // Highlight temporaire d'un élément
        handleHighlight: function(action) {
            var selector = action.selector || action.target;
            var elements = document.querySelectorAll(selector);

            elements.forEach(function(el) {
                el.classList.add('action-highlight');

                setTimeout(function() {
                    el.classList.remove('action-highlight');
                }, action.duration || 2000);
            });
        },

        // Télécharger un fichier
        handleDownload: function(action) {
            var url = action.url || action.file;
            var filename = action.filename || 'download';

            this.showActionNotification('Téléchargement en cours...', 'download');

            var link = document.createElement('a');
            link.href = url;
            link.download = filename;
            link.target = '_blank';
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        },

        // Ouvrir un lien externe
        handleOpenLink: function(action) {
            var url = action.url || CONFIG.EXTERNAL_LINKS[action.target] || action.target;

            if (url) {
                this.showActionNotification('Ouverture dans un nouvel onglet...', 'link');

                setTimeout(function() {
                    window.open(url, '_blank', 'noopener,noreferrer');
                }, 500);
            }
        },

        // Afficher le formulaire de contact
        handleShowContact: function(action) {
            var contactSection = document.querySelector('#contact') ||
                                 document.querySelector('.contact-section') ||
                                 document.querySelector('[data-section="contact"]');

            if (contactSection) {
                this.closeChatbot();

                setTimeout(function() {
                    contactSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
                }, CONFIG.SCROLL_DELAY);
            } else {
                // Rediriger vers la page contact
                window.location.href = CONFIG.ROUTES.contact;
            }
        },

        // Afficher une notification
        handleShowNotification: function(action) {
            this.showActionNotification(action.message, action.notificationType || 'info');
        },

        // Toggle un élément (show/hide)
        handleToggleElement: function(action) {
            var element = document.querySelector(action.selector || action.target);

            if (element) {
                element.classList.toggle('hidden');
                element.classList.toggle('visible');
            }
        },

        // Jouer une animation
        handlePlayAnimation: function(action) {
            var element = document.querySelector(action.selector || action.target);
            var animationClass = action.animation || 'animate-pulse';

            if (element) {
                element.classList.add(animationClass);

                setTimeout(function() {
                    element.classList.remove(animationClass);
                }, action.duration || 1000);
            }
        },

        // Copier dans le presse-papier
        handleCopyToClipboard: function(action) {
            var text = action.data || action.text;
            var self = this;

            navigator.clipboard.writeText(text).then(function() {
                self.showActionNotification(action.message || 'Copié dans le presse-papier!', 'success');
            }).catch(function() {
                // Fallback pour navigateurs plus anciens
                var textarea = document.createElement('textarea');
                textarea.value = text;
                document.body.appendChild(textarea);
                textarea.select();
                document.execCommand('copy');
                document.body.removeChild(textarea);
                self.showActionNotification(action.message || 'Copié!', 'success');
            });
        },

        // Ouvrir la page témoignage
        handleOpenTestimonial: function(action) {
            this.showActionNotification('Ouverture du formulaire de témoignage...', 'redirect');

            setTimeout(function() {
                window.location.href = CONFIG.ROUTES.testimonial;
            }, CONFIG.REDIRECT_DELAY);
        },

        // Fermer le chatbot
        closeChatbot: function() {
            if (window.chatbot && window.chatbot.isOpen) {
                window.chatbot.toggleWindow();
            }
        },

        // Créer un modal dynamique
        createDynamicModal: function(action) {
            var overlay = document.createElement('div');
            overlay.className = 'action-modal-overlay';
            overlay.innerHTML =
                '<div class="action-modal">' +
                    '<button class="action-modal-close">&times;</button>' +
                    '<div class="action-modal-content">' +
                        (action.title ? '<h3>' + action.title + '</h3>' : '') +
                        (action.content ? '<div>' + action.content + '</div>' : '') +
                    '</div>' +
                '</div>';

            document.body.appendChild(overlay);

            // Fermer au clic
            overlay.addEventListener('click', function(e) {
                if (e.target === overlay || e.target.classList.contains('action-modal-close')) {
                    overlay.classList.add('closing');
                    setTimeout(function() {
                        document.body.removeChild(overlay);
                    }, 300);
                }
            });

            // Animation d'entrée
            requestAnimationFrame(function() {
                overlay.classList.add('active');
            });
        },

        // Afficher une notification d'action
        showActionNotification: function(message, type) {
            type = type || 'info';

            // Supprimer notification existante
            var existing = document.querySelector('.action-notification');
            if (existing) {
                existing.remove();
            }

            var icons = {
                redirect: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>',
                download: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>',
                success: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>',
                link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
                info: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="16" x2="12" y2="12"/><line x1="12" y1="8" x2="12.01" y2="8"/></svg>'
            };

            var notification = document.createElement('div');
            notification.className = 'action-notification action-notification--' + type;
            notification.innerHTML =
                '<span class="action-notification-icon">' + (icons[type] || icons.info) + '</span>' +
                '<span class="action-notification-message">' + message + '</span>';

            document.body.appendChild(notification);

            // Animation d'entrée
            requestAnimationFrame(function() {
                notification.classList.add('visible');
            });

            // Auto-hide
            setTimeout(function() {
                notification.classList.remove('visible');
                setTimeout(function() {
                    if (notification.parentNode) {
                        notification.parentNode.removeChild(notification);
                    }
                }, 300);
            }, CONFIG.NOTIFICATION_DURATION);
        }
    };

    // ==========================================
    // Response Parser
    // ==========================================
    var ResponseParser = {

        // Parser une réponse pour extraire les actions
        parse: function(response) {
            var actions = [];

            // 1. Chercher des actions JSON structurées dans la réponse
            var jsonActions = this.extractJsonActions(response);
            if (jsonActions.length > 0) {
                actions = actions.concat(jsonActions);
            }

            // 2. Chercher des tags d'action [[ACTION:type:data]]
            var tagActions = this.extractTagActions(response);
            if (tagActions.length > 0) {
                actions = actions.concat(tagActions);
            }

            // 3. Détecter des intentions dans le texte
            var intentActions = this.detectIntentActions(response);
            if (intentActions.length > 0) {
                actions = actions.concat(intentActions);
            }

            return actions;
        },

        // Extraire les actions JSON
        extractJsonActions: function(response) {
            var actions = [];

            // Chercher un bloc JSON d'actions
            var jsonMatch = response.match(/\[\[ACTIONS:(.*?)\]\]/s);
            if (jsonMatch) {
                try {
                    var parsed = JSON.parse(jsonMatch[1]);
                    if (Array.isArray(parsed)) {
                        actions = parsed;
                    } else {
                        actions = [parsed];
                    }
                } catch (e) {
                    log('Erreur parsing JSON actions:', e);
                }
            }

            return actions;
        },

        // Extraire les tags d'action [[ACTION:type:data]]
        extractTagActions: function(response) {
            var actions = [];
            var tagRegex = /\[\[ACTION:(\w+)(?::([^\]]+))?\]\]/g;
            var match;

            while ((match = tagRegex.exec(response)) !== null) {
                var action = {
                    type: match[1].toLowerCase()
                };

                // Parser les données
                if (match[2]) {
                    var params = match[2].split(':');
                    if (params.length === 1) {
                        action.target = params[0];
                    } else {
                        action.target = params[0];
                        action.data = params.slice(1).join(':');
                    }
                }

                actions.push(action);
            }

            return actions;
        },

        // Détecter les intentions dans le texte
        detectIntentActions: function(response) {
            var actions = [];
            var text = response.toLowerCase();

            IntentPatterns.forEach(function(intent) {
                intent.patterns.forEach(function(pattern) {
                    if (pattern.test(text)) {
                        // Éviter les doublons
                        var isDuplicate = actions.some(function(a) {
                            return a.type === intent.action.type && a.target === intent.action.target;
                        });

                        if (!isDuplicate) {
                            actions.push(Object.assign({}, intent.action));
                        }
                    }
                });
            });

            return actions;
        },

        // Nettoyer la réponse des tags d'action
        cleanResponse: function(response) {
            return response
                .replace(/\[\[ACTIONS:.*?\]\]/gs, '')
                .replace(/\[\[ACTION:\w+(?::[^\]]+)?\]\]/g, '')
                .trim();
        }
    };

    // ==========================================
    // Main Interceptor
    // ==========================================
    var ChatbotInterceptor = {
        originalHandlers: {},

        // Initialiser l'intercepteur
        init: function() {
            log('Initialisation intercepteur...');
            this.hookIntoChatbot();
            this.injectStyles();
            this.setupUrlParamActions();
            log('Intercepteur initialisé');
        },

        // Se connecter au chatbot
        hookIntoChatbot: function() {
            var self = this;

            // Attendre que le chatbot soit disponible
            var checkInterval = setInterval(function() {
                if (window.chatbot) {
                    clearInterval(checkInterval);
                    self.attachHooks();
                }
            }, 100);

            // Timeout après 10 secondes
            setTimeout(function() {
                clearInterval(checkInterval);
            }, 10000);
        },

        // Attacher les hooks aux méthodes du chatbot
        attachHooks: function() {
            var self = this;
            var chatbot = window.chatbot;

            // Hook sur addBotMessage
            if (chatbot.addBotMessage) {
                this.originalHandlers.addBotMessage = chatbot.addBotMessage.bind(chatbot);

                chatbot.addBotMessage = function(content, animate) {
                    // Parser la réponse pour les actions
                    var actions = ResponseParser.parse(content);

                    // Nettoyer le contenu des tags d'action
                    var cleanContent = ResponseParser.cleanResponse(content);

                    // Appeler la méthode originale
                    self.originalHandlers.addBotMessage(cleanContent, animate);

                    // Exécuter les actions avec un délai
                    if (actions.length > 0) {
                        log('Actions détectées:', actions);

                        setTimeout(function() {
                            self.executeActions(actions);
                        }, 800);
                    }
                };
            }

            // Hook sur appendToStreamingMessage pour le streaming
            if (chatbot.appendToStreamingMessage) {
                var streamBuffer = '';
                this.originalHandlers.appendToStreamingMessage = chatbot.appendToStreamingMessage.bind(chatbot);

                chatbot.appendToStreamingMessage = function(messageElement, chunk) {
                    streamBuffer += chunk;
                    self.originalHandlers.appendToStreamingMessage(messageElement, chunk);
                };

                // Hook sur finalizeStreamingMessage
                if (chatbot.finalizeStreamingMessage) {
                    this.originalHandlers.finalizeStreamingMessage = chatbot.finalizeStreamingMessage.bind(chatbot);

                    chatbot.finalizeStreamingMessage = function(messageElement) {
                        self.originalHandlers.finalizeStreamingMessage(messageElement);

                        // Parser le buffer complet
                        var actions = ResponseParser.parse(streamBuffer);

                        if (actions.length > 0) {
                            log('Actions détectées (streaming):', actions);

                            setTimeout(function() {
                                self.executeActions(actions);
                            }, 800);
                        }

                        // Reset buffer
                        streamBuffer = '';
                    };
                }
            }

            log('Hooks attachés au chatbot');
        },

        // Exécuter une liste d'actions
        executeActions: function(actions) {
            actions.forEach(function(action, index) {
                // Délai entre les actions multiples
                setTimeout(function() {
                    ActionExecutor.execute(action);
                }, index * 500);
            });
        },

        // Gérer les actions via paramètres URL
        setupUrlParamActions: function() {
            var params = new URLSearchParams(window.location.search);

            // ?highlight=project-id
            var highlight = params.get('highlight');
            if (highlight) {
                setTimeout(function() {
                    ActionExecutor.execute({
                        type: ActionTypes.SHOW_PROJECT,
                        projectId: highlight
                    });
                }, 500);
            }

            // ?action=scroll&target=#skills
            var action = params.get('action');
            var target = params.get('target');
            if (action && target) {
                setTimeout(function() {
                    ActionExecutor.execute({
                        type: action,
                        target: target
                    });
                }, 500);
            }

            // ?contact=true
            if (params.get('contact') === 'true') {
                setTimeout(function() {
                    ActionExecutor.execute({ type: ActionTypes.SHOW_CONTACT });
                }, 500);
            }
        },

        // Injecter les styles CSS
        injectStyles: function() {
            var styles = document.createElement('style');
            styles.textContent = '\n' +
                '/* Action Notification */\n' +
                '.action-notification {\n' +
                '    position: fixed;\n' +
                '    bottom: 100px;\n' +
                '    right: 24px;\n' +
                '    padding: 14px 20px;\n' +
                '    background: #161616;\n' +
                '    border: 1px solid #252525;\n' +
                '    border-radius: 12px;\n' +
                '    color: #ffffff;\n' +
                '    font-family: "Space Grotesk", sans-serif;\n' +
                '    font-size: 14px;\n' +
                '    display: flex;\n' +
                '    align-items: center;\n' +
                '    gap: 10px;\n' +
                '    z-index: 99998;\n' +
                '    opacity: 0;\n' +
                '    transform: translateY(20px);\n' +
                '    transition: all 0.3s ease;\n' +
                '    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);\n' +
                '}\n' +
                '.action-notification.visible {\n' +
                '    opacity: 1;\n' +
                '    transform: translateY(0);\n' +
                '}\n' +
                '.action-notification-icon {\n' +
                '    width: 20px;\n' +
                '    height: 20px;\n' +
                '    color: #00ff88;\n' +
                '}\n' +
                '.action-notification-icon svg {\n' +
                '    width: 100%;\n' +
                '    height: 100%;\n' +
                '}\n' +
                '.action-notification--success { border-color: #00ff88; }\n' +
                '.action-notification--success .action-notification-icon { color: #00ff88; }\n' +
                '.action-notification--redirect { border-color: #3b82f6; }\n' +
                '.action-notification--redirect .action-notification-icon { color: #3b82f6; }\n' +
                '.action-notification--download { border-color: #f59e0b; }\n' +
                '.action-notification--download .action-notification-icon { color: #f59e0b; }\n' +
                '\n' +
                '/* Action Highlight */\n' +
                '.action-highlight {\n' +
                '    animation: actionPulse 0.6s ease-in-out 3;\n' +
                '    box-shadow: 0 0 0 4px rgba(0, 255, 136, 0.3) !important;\n' +
                '}\n' +
                '@keyframes actionPulse {\n' +
                '    0%, 100% { box-shadow: 0 0 0 4px rgba(0, 255, 136, 0.3); }\n' +
                '    50% { box-shadow: 0 0 0 8px rgba(0, 255, 136, 0.1); }\n' +
                '}\n' +
                '.project-spotlight {\n' +
                '    transform: scale(1.02);\n' +
                '    transition: transform 0.3s ease;\n' +
                '}\n' +
                '.skill-spotlight {\n' +
                '    background: rgba(0, 255, 136, 0.1) !important;\n' +
                '}\n' +
                '\n' +
                '/* Action Modal */\n' +
                '.action-modal-overlay {\n' +
                '    position: fixed;\n' +
                '    inset: 0;\n' +
                '    background: rgba(0, 0, 0, 0.8);\n' +
                '    backdrop-filter: blur(4px);\n' +
                '    z-index: 99999;\n' +
                '    display: flex;\n' +
                '    align-items: center;\n' +
                '    justify-content: center;\n' +
                '    padding: 24px;\n' +
                '    opacity: 0;\n' +
                '    transition: opacity 0.3s ease;\n' +
                '}\n' +
                '.action-modal-overlay.active { opacity: 1; }\n' +
                '.action-modal-overlay.closing { opacity: 0; }\n' +
                '.action-modal {\n' +
                '    background: #0f0f0f;\n' +
                '    border: 1px solid #252525;\n' +
                '    border-radius: 20px;\n' +
                '    padding: 32px;\n' +
                '    max-width: 500px;\n' +
                '    width: 100%;\n' +
                '    position: relative;\n' +
                '    transform: scale(0.95);\n' +
                '    transition: transform 0.3s ease;\n' +
                '}\n' +
                '.action-modal-overlay.active .action-modal { transform: scale(1); }\n' +
                '.action-modal-close {\n' +
                '    position: absolute;\n' +
                '    top: 16px;\n' +
                '    right: 16px;\n' +
                '    width: 32px;\n' +
                '    height: 32px;\n' +
                '    border: none;\n' +
                '    background: #1a1a1a;\n' +
                '    border-radius: 8px;\n' +
                '    color: #666;\n' +
                '    font-size: 20px;\n' +
                '    cursor: pointer;\n' +
                '    transition: all 0.2s ease;\n' +
                '}\n' +
                '.action-modal-close:hover { background: #252525; color: #fff; }\n' +
                '.action-modal-content h3 {\n' +
                '    font-family: "Syne", sans-serif;\n' +
                '    font-size: 24px;\n' +
                '    margin-bottom: 16px;\n' +
                '    color: #fff;\n' +
                '}\n' +
                '.action-modal-content {\n' +
                '    color: #a0a0a0;\n' +
                '    line-height: 1.6;\n' +
                '}\n' +
                '\n' +
                '/* Mobile adjustments */\n' +
                '@media (max-width: 480px) {\n' +
                '    .action-notification {\n' +
                '        left: 16px;\n' +
                '        right: 16px;\n' +
                '        bottom: 90px;\n' +
                '    }\n' +
                '}\n';

            document.head.appendChild(styles);
        }
    };

    // ==========================================
    // API Publique
    // ==========================================
    window.ChatbotActions = {
        // Exécuter une action manuellement
        execute: function(action) {
            ActionExecutor.execute(action);
        },

        // Exécuter plusieurs actions
        executeAll: function(actions) {
            ChatbotInterceptor.executeActions(actions);
        },

        // Rediriger vers une page
        redirect: function(target) {
            ActionExecutor.execute({ type: ActionTypes.REDIRECT, target: target });
        },

        // Scroll vers un élément
        scrollTo: function(selector) {
            ActionExecutor.execute({ type: ActionTypes.SCROLL_TO, target: selector });
        },

        // Afficher une notification
        notify: function(message, type) {
            ActionExecutor.showActionNotification(message, type);
        },

        // Copier dans le presse-papier
        copyToClipboard: function(text, message) {
            ActionExecutor.execute({
                type: ActionTypes.COPY_TO_CLIPBOARD,
                data: text,
                message: message
            });
        },

        // Ouvrir un lien
        openLink: function(url) {
            ActionExecutor.execute({ type: ActionTypes.OPEN_LINK, url: url });
        },

        // Afficher un projet
        showProject: function(projectId) {
            ActionExecutor.execute({ type: ActionTypes.SHOW_PROJECT, projectId: projectId });
        },

        // Types d'actions disponibles
        types: ActionTypes,

        // Configuration
        config: CONFIG
    };

    // ==========================================
    // Initialisation
    // ==========================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            ChatbotInterceptor.init();
        });
    } else {
        ChatbotInterceptor.init();
    }

})();