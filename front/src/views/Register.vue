<template>
  <div class="register-container">
    <h2>Register</h2>
    <form @submit.prevent="submitForm">
      <div>
        <label for="email">Email</label>
        <input type="email" id="email" v-model="email" required />
      </div>
      <div>
        <label for="password">Password</label>
        <input type="password" id="password" v-model="password" required />
      </div>
      <div>
        <label for="confirm-password">Confirm Password</label>
        <input
          type="password"
          id="confirm-password"
          v-model="confirmPassword"
          required
        />
      </div>
      <button type="submit">Register</button>
    </form>
  </div>
</template>

<script>
import { $ajax } from "../services/api";

export default {
  data() {
    return {
      email: "",
      password: "",
      confirmPassword: "",
    };
  },
  methods: {
    async submitForm() {
      if (this.password == this.confirmPassword) {
        $ajax({
          url: "/auth/registration/",
          method: "POST",
          data: {
            email: this.email,
            password1: this.password,
            password2: this.confirmPassword,
          },
          xhrFields: {
            withCredentials: true,
          },
          success: () => {
            $ajax({
              url: "/auth/login/",
              method: "POST",
              data: {
                email: this.email,
                password: this.password,
              },
              xhrFields: {
                withCredentials: true,
              },
              success: () => {
                $ajax({
                  url: "/uuid",
                  method: "GET",
                  data: {
                    email: this.email,
                  },
                  xhrFields: {
                    withCredentials: true,
                  },
                  success: (response) => {
                    this.$notify({
                      title: "Login successful",
                      text: "You have successfully logged in! Click here to go back to default page.",
                      type: "success",
                      group: "login-success",
                      duration: 50000,
                    });
                    localStorage.setItem("email", this.email);
                    localStorage.setItem("uuid", response);

                    window.history.pushState({}, "", "/admin");
                    window.location.reload();
                  },
                });
              },
              error: (error) => {
                this.$notify({
                  title: "Login failed",
                  text: "Please check your credentials and try again.",
                  type: "error",
                  duration: 5000, // notification will disappear after 5 seconds
                });
                console.error(error);
              },
            });
          },
          error: (error) => {
            const e = error?.responseJSON;
            if (!e || typeof e !== "object") {
              this.$notify({
                title: "Registration failed",
                text: "Please check your inputs and try again.",
                type: "error",
                duration: 8000,
              });
              console.error("Non-JSON error:", error);
              return;
            }

            const first = (v) => (Array.isArray(v) ? v[0] : v);

            let title = "Registration failed";
            if (e.email) title = "Email already in use";
            else if (e.password2) title = "Passwords do not match";
            else if (e.password1) title = "Weak password";
            else if (e.non_field_errors) title = "Registration error";

            const text =
              first(e.email) ||
              first(e.password1) ||
              first(e.password2) ||
              first(e.non_field_errors) ||
              e.detail ||
              "Please check your inputs and try again.";

            this.$notify({ title, text, type: "error", duration: 5000 });
            console.error("Registration error:", e);
          },
        });
      } else {
        this.$notify({
          title: "Please make sure your passwords match. ",
          type: "error",
          duration: 5000, // notification will disappear after 5 seconds
        });
      }
    },
  },
};
</script>

<style>
.register-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  width: 100vw;
}

.register-container > h2 {
  margin-bottom: 20px;
}
</style>
