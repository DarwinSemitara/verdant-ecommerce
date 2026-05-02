// ============================================================================
// LOGIN PAGE FUNCTIONALITY
// ============================================================================

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeLoginPage();
});

function initializeLoginPage() {
    setupEventListeners();
    setupPasswordToggles();
}

function setupEventListeners() {
    // Signup link
    const signupLink = document.querySelector('.signup-link');
    if (signupLink) {
        signupLink.addEventListener('click', function(e) {
            e.preventDefault();
            showSignupModal();
        });
    }

    // Forgot password link
    const forgotLink = document.querySelector('.forgot-password');
    if (forgotLink) {
        forgotLink.addEventListener('click', function(e) {
            e.preventDefault();
            showForgotModal();
        });
    }
    
    // Help button
    const infoToggle = document.getElementById('infoToggle');
    if (infoToggle) {
        infoToggle.addEventListener('click', showInfoModal);
    }
    
    // Modal close buttons
    setupModalCloseButtons();
    
    // Terms agreement checkbox
    const agreeTermsCheckbox = document.getElementById('agreeTerms');
    if (agreeTermsCheckbox) {
        agreeTermsCheckbox.addEventListener('change', function() {
            const continueBtn = document.getElementById('continueToRole');
            if (continueBtn) {
                continueBtn.disabled = !this.checked;
            }
        });
    }
    
    // Continue to role selection button
    const continueToRoleBtn = document.getElementById('continueToRole');
    if (continueToRoleBtn) {
        continueToRoleBtn.addEventListener('click', function(e) {
            e.preventDefault();
            showRoleSelection('roleSelect');
        });
    }
    
    // Role selection
    setupRoleSelection();
    
    // Role form header buttons (close inside forms)
    setupRoleFormHeaderButtons();

    // Form validation
    setupFormValidation();

    // Help modal role tabs
    setupHelpRoleTabs();
}

function setupPasswordToggles() {
    const passwordInputs = document.querySelectorAll('.password-with-toggle');
    passwordInputs.forEach(input => {
        const toggle = document.createElement('button');
        toggle.type = 'button';
        toggle.innerHTML = '';
        toggle.style.cssText = `
            position: absolute;
            right: 10px;
            top: 50%;
            transform: translateY(-50%);
            background: none;
            border: none;
            cursor: pointer;
            font-size: 16px;
        `;
        
        const wrapper = document.createElement('div');
        wrapper.style.position = 'relative';
        input.parentNode.insertBefore(wrapper, input);
        wrapper.appendChild(input);
        wrapper.appendChild(toggle);
        
        toggle.addEventListener('click', function() {
            if (input.type === 'password') {
                input.type = 'text';
                toggle.innerHTML = '';
            } else {
                input.type = 'password';
                toggle.innerHTML = '';
            }
        });
    });
}

function setupRoleSelection() {
    const roleButtons = {
        'chooseUser': 'userFormContainer',
        'chooseSeller': 'sellerFormContainer',
        'chooseRider': 'riderFormContainer'
    };
    
    Object.keys(roleButtons).forEach(buttonId => {
        const button = document.getElementById(buttonId);
        if (button) {
            button.addEventListener('click', function() {
                showRoleForm(roleButtons[buttonId]);
            });
        }
    });
    
    // Back to role selection
    const backButtons = document.querySelectorAll('.back-to-select');
    backButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            const target = this.getAttribute('data-target');
            showRoleSelection(target);
        });
    });
}

function setupRoleFormHeaderButtons() {
    const closeButtons = document.querySelectorAll('.role-header-close');
    closeButtons.forEach(btn => {
        btn.addEventListener('click', function(e) {
            e.preventDefault();
            hideSignupModal();
        });
    });
}

function setupHelpRoleTabs() {
    const tabButtons = document.querySelectorAll('.help-role-tab');
    const panels = document.querySelectorAll('.help-role-panel');

    if (!tabButtons.length || !panels.length) {
        return;
    }

    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const role = button.getAttribute('data-role');
            if (!role) return;

            tabButtons.forEach(b => b.classList.remove('active'));
            panels.forEach(p => p.classList.remove('active'));

            button.classList.add('active');
            const targetPanel = document.getElementById(`helpRole_${role}`);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }
        });
    });
}

function showRoleForm(formId) {
    // Hide all forms
    const allForms = ['termsStep', 'roleSelect', 'userFormContainer', 'sellerFormContainer', 'riderFormContainer'];
    allForms.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.style.display = 'none';
        }
    });
    
    // Show selected form
    const selectedForm = document.getElementById(formId);
    if (selectedForm) {
        selectedForm.style.display = 'block';
    }

    // Hide main signup header when inside a specific role form
    setSignupHeaderVisible(false);
}

function showRoleSelection(targetId) {
    // Hide all forms
    const allForms = ['termsStep', 'roleSelect', 'userFormContainer', 'sellerFormContainer', 'riderFormContainer'];
    allForms.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.style.display = 'none';
        }
    });
    
    // Show role selection
    const roleSelect = document.getElementById(targetId || 'roleSelect');
    if (roleSelect) {
        roleSelect.style.display = 'block';
    }

    // Show the main signup header when choosing a role
    setSignupHeaderVisible(true);
    setSignupTitle('Create Account');
}

function showTermsStep() {
    // Hide all forms
    const allForms = ['termsStep', 'roleSelect', 'userFormContainer', 'sellerFormContainer', 'riderFormContainer'];
    allForms.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.style.display = 'none';
        }
    });
    
    // Show terms step
    const termsStep = document.getElementById('termsStep');
    if (termsStep) {
        termsStep.style.display = 'block';
    }
    setSignupHeaderVisible(true);
    setSignupTitle('Create Account');
}

function setSignupTitle(text) {
    const header = document.querySelector('#signupModal h2');
    if (header && typeof text === 'string') {
        header.textContent = text;
    }
}

function setSignupHeaderVisible(visible) {
    const header = document.querySelector('#signupModal h2');
    if (header) {
        header.style.display = visible ? 'block' : 'none';
    }
}

function setupFormValidation() {
    // Password confirmation validation
    const passwordInputs = document.querySelectorAll('input[type="password"]');
    passwordInputs.forEach(input => {
        input.addEventListener('input', validatePasswordMatch);
    });
    
    // Form submission validation - exclude forms with no-validation class
    const forms = document.querySelectorAll('form:not(.no-validation)');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!validateForm(this)) {
                e.preventDefault();
            }
        });
    });
}

function validatePasswordMatch() {
    const passwordInputs = this.parentElement.querySelectorAll('input[type="password"]');
    if (passwordInputs.length === 2) {
        const password = passwordInputs[0].value;
        const confirmPassword = passwordInputs[1].value;
        
        if (confirmPassword && password !== confirmPassword) {
            this.setCustomValidity('Passwords do not match');
        } else {
            this.setCustomValidity('');
        }
    }
}

function validateForm(form) {
    const requiredFields = form.querySelectorAll('input[required], select[required]');
    let isValid = true;
    
    requiredFields.forEach(field => {
        if (!field.value.trim()) {
            field.setCustomValidity('This field is required');
            isValid = false;
        } else {
            field.setCustomValidity('');
        }
    });
    
    return isValid;
}

// ============================================================================
// MODAL FUNCTIONS
// ============================================================================

function showSignupModal() {
    const modal = document.getElementById('signupModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
        
        // Reset to terms step
        showTermsStep();
    }
}

function hideSignupModal() {
    const modal = document.getElementById('signupModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

function showInfoModal() {
    const modal = document.getElementById('infoModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function hideInfoModal() {
    const modal = document.getElementById('infoModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

function showErrorModal(message) {
    const modal = document.getElementById('errorModal');
    const errorMessage = document.getElementById('errorMessage');
    if (modal && errorMessage) {
        errorMessage.textContent = message;
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function hideErrorModal() {
    const modal = document.getElementById('errorModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

function setupModalCloseButtons() {
    // Info modal
    const closeInfo = document.getElementById('closeInfo');
    if (closeInfo) {
        closeInfo.addEventListener('click', hideInfoModal);
    }
    
    // Signup modal
    const closeSignup = document.getElementById('closeSignup');
    if (closeSignup) {
        closeSignup.addEventListener('click', hideSignupModal);
    }
    
    // Forgot password modal
    const closeForgot = document.getElementById('closeForgot');
    if (closeForgot) {
        closeForgot.addEventListener('click', hideForgotModal);
    }
    
    // Error modal
    const closeError = document.getElementById('closeError');
    if (closeError) {
        closeError.addEventListener('click', hideErrorModal);
    }
    
    // Close modals when clicking outside (but keep signup modal persistent)
    document.addEventListener('click', function(event) {
        if (event.target.classList.contains('info-modal') ||
            event.target.classList.contains('error-modal') ||
            event.target.classList.contains('forgot-modal')) {
            event.target.style.display = 'none';
            document.body.style.overflow = 'auto';
        }
    });

    // Close modals with Escape key (excluding signup modal to avoid accidental loss of form data)
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            ['info-modal', 'error-modal', 'forgot-modal'].forEach(cls => {
                document.querySelectorAll('.' + cls).forEach(modalEl => {
                    if (getComputedStyle(modalEl).display === 'flex') {
                        modalEl.style.display = 'none';
                        document.body.style.overflow = 'auto';
                    }
                });
            });
        }
    });
}

// ============================================================================
// FORGOT PASSWORD MODAL & FLOW
// ============================================================================

function showForgotModal() {
    const modal = document.getElementById('forgotModal');
    const stepPhone = document.getElementById('forgotStepPhone');
    const stepCode = document.getElementById('forgotStepCode');
    const message = document.getElementById('forgotMessage');

    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }

    if (stepPhone && stepCode) {
        stepPhone.style.display = 'block';
        stepCode.style.display = 'none';
    }

    if (message) {
        message.textContent = '';
    }

    const emailInput = document.getElementById('forgot-email');
    const codeInput = document.getElementById('forgot-code');
    const newPass = document.getElementById('forgot-new-password');
    const confirmPass = document.getElementById('forgot-confirm-password');
    if (emailInput) emailInput.value = '';
    if (codeInput) codeInput.value = '';
    if (newPass) newPass.value = '';
    if (confirmPass) confirmPass.value = '';

    const sendBtn = document.getElementById('sendOtpButton');
    const resetBtn = document.getElementById('resetPasswordButton');

    if (sendBtn && !sendBtn._forgotBound) {
        sendBtn.addEventListener('click', handleSendOtp);
        sendBtn._forgotBound = true;
    }

    if (resetBtn && !resetBtn._forgotBound) {
        resetBtn.addEventListener('click', handleResetPassword);
        resetBtn._forgotBound = true;
    }
}

function hideForgotModal() {
    const modal = document.getElementById('forgotModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

function handleSendOtp() {
    const emailInput = document.getElementById('forgot-email');
    const message = document.getElementById('forgotMessage');
    const stepPhone = document.getElementById('forgotStepPhone');
    const stepCode = document.getElementById('forgotStepCode');

    if (!emailInput || !emailInput.value.trim()) {
        if (message) message.textContent = 'Please enter your email address.';
        return;
    }

    fetch('/forgot-password', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: emailInput.value.trim() })
    })
    .then(response => response.json())
    .then(data => {
        if (message) {
            message.textContent = data.message || '';
        }
        if (data.success) {
            if (stepPhone && stepCode) {
                stepPhone.style.display = 'none';
                stepCode.style.display = 'block';
            }
        }
    })
    .catch(() => {
        if (message) {
            message.textContent = 'An error occurred while sending the verification code.';
        }
    });
}

function handleResetPassword() {
    const codeInput = document.getElementById('forgot-code');
    const newPass = document.getElementById('forgot-new-password');
    const confirmPass = document.getElementById('forgot-confirm-password');
    const message = document.getElementById('forgotMessage');

    if (!codeInput || !codeInput.value.trim()) {
        if (message) message.textContent = 'Please enter the verification code.';
        return;
    }

    if (!newPass || !newPass.value) {
        if (message) message.textContent = 'Please enter a new password.';
        return;
    }

    if (!confirmPass || !confirmPass.value || newPass.value !== confirmPass.value) {
        if (message) message.textContent = 'Passwords do not match.';
        return;
    }

    fetch('/reset-password', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            code: codeInput.value.trim(),
            new_password: newPass.value
        })
    })
    .then(response => response.json())
    .then(data => {
        if (message) {
            message.textContent = data.message || '';
        }
        if (data.success) {
            // Close modal after successful reset
            setTimeout(() => {
                hideForgotModal();
            }, 1000);
        }
    })
    .catch(() => {
        if (message) {
            message.textContent = 'An error occurred while resetting your password.';
        }
    });
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

function showNotification(message, type = 'info', durationMs = 4000) {
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    notification.style.cssText = `
        position: fixed !important;
        top: 20px !important;
        right: 20px !important;
        background: ${type === 'error' ? '#dc3545' : type === 'success' ? '#28a745' : '#17a2b8'};
        color: white;
        padding: 1rem 1.5rem;
        border-radius: 0.5rem;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
        z-index: 999999 !important;
        max-width: 350px;
        animation: slideInRight 0.3s ease;
        pointer-events: auto;
        font-weight: 600;
        font-size: 1rem;
    `;
    
    // Always append to body, not to any container
    document.body.appendChild(notification);
    
    // Remove after the requested duration
    const timeout = typeof durationMs === 'number' && durationMs > 0 ? durationMs : 4000;
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => {
            if (notification.parentNode) {
                document.body.removeChild(notification);
            }
        }, 300);
    }, timeout);
}

// Add CSS animations and notification styles
const style = document.createElement('style');
style.textContent = `
    .notification {
        position: fixed !important;
        top: 20px !important;
        right: 20px !important;
        z-index: 999999 !important;
        max-width: 350px !important;
        pointer-events: auto !important;
    }
    
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// ============================================================================
// PASSWORD TOGGLE FUNCTION
// ============================================================================

function togglePassword(inputId) {
    const input = document.getElementById(inputId);
    const button = input.nextElementSibling;
    
    if (input.type === 'password') {
        input.type = 'text';
        button.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path>
                <line x1="1" y1="1" x2="23" y2="23"></line>
            </svg>
        `;
    } else {
        input.type = 'password';
        button.innerHTML = `
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                <circle cx="12" cy="12" r="3"></circle>
            </svg>
        `;
    }
}