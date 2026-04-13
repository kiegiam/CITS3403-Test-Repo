const loginForm = document.getElementById("loginForm");
const emailInput = document.getElementById("email");
const passwordInput = document.getElementById("password");
const emailError = document.getElementById("emailError");
const passwordError = document.getElementById("passwordError");

function validateEmail() {
    const email = emailInput.value.trim();

    if (email === "") {
        emailError.textContent = "Email is required.";
        return false;
    }

    emailError.textContent = "";
    return true;
}

function validatePassword() {
    const password = passwordInput.value;

    if (password === "") {
        passwordError.textContent = "Password is required.";
        return false;
    }

    if (password.length < 6) {
        passwordError.textContent = "Password must be at least 6 characters.";
        return false;
    }

    passwordError.textContent = "";
    return true;
}

emailInput.addEventListener("input", validateEmail);
passwordInput.addEventListener("input", validatePassword);

loginForm.addEventListener("submit", function (event) {
    const isEmailValid = validateEmail();
    const isPasswordValid = validatePassword();

    if (!isEmailValid || !isPasswordValid) {
        event.preventDefault();
    }
});