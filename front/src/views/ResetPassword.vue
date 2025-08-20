<template>
  <div class="reset-container">
    <h2>Reset Password</h2>

    <form @submit.prevent="submitForm" class="form">
      <div class="form-row">
        <label for="email">Email</label>
        <input
          id="email"
          type="email"
          v-model.trim="email"
          required
          placeholder="you@example.com"
        />
      </div>

      <button type="submit" :disabled="loading">
        {{ loading ? "Sending..." : "Send reset link" }}
      </button>
    </form>

    <p v-if="successMessage" class="success">{{ successMessage }}</p>
    <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
  </div>
</template>

<script>
import { $ajax } from "../services/api";

export default {
  name: "ResetPassword",
  data() {
    return {
      email: "",
      loading: false,
      successMessage: "",
      errorMessage: "",
    };
  },
  methods: {
    async submitForm() {
      this.successMessage = "";
      this.errorMessage = "";
      this.loading = true;

      const email = (this.email || "").trim().toLowerCase();

      $ajax({
        url: "/auth/password/reset/",
        method: "POST",
        data: { email },
        xhrFields: { withCredentials: true },
        success: () => {
          this.successMessage =
            "If the email is registered, a reset link has been sent.";
          this.$notify({
            title: "Request sent",
            text: "If registered, the reset link has been sent (in dev, check the server console).",
            type: "success",
          });
        },
        error: (xhr) => {
          try {
            const payload = xhr.responseJSON || {};
            const detail =
              payload?.detail ||
              (Array.isArray(payload?.email) ? payload.email.join(", ") : "") ||
              "An error occurred.";
            this.errorMessage = detail;
          } catch (e) {
            this.errorMessage = "An error occurred.";
          }
        },
        complete: () => {
          this.loading = false;
        },
      });
    },
  },
};
</script>
