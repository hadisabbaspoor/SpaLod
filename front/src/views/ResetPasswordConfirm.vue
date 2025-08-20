<template>
  <div class="reset-confirm">
    <h2>Set a New Password</h2>

    <form @submit.prevent="submitForm" class="form">
      <div class="form-row">
        <label for="p1">New password</label>
        <input
          id="p1"
          :type="show ? 'text' : 'password'"
          v-model.trim="p1"
          autocomplete="new-password"
          required
        />
      </div>

      <div class="form-row">
        <label for="p2">Confirm password</label>
        <input
          id="p2"
          :type="show ? 'text' : 'password'"
          v-model.trim="p2"
          autocomplete="new-password"
          required
        />
      </div>

      <label class="show-row">
        <input type="checkbox" v-model="show" />
        Show passwords
      </label>

      <button type="submit" :disabled="loading">
        {{ loading ? "Saving..." : "Save new password" }}
      </button>
    </form>

    <p v-if="success" class="success">
      Your password has been updated. You can now sign in.
    </p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script>
import { $ajax } from "../services/api";

export default {
  name: "ResetPasswordConfirm",
  data() {
    return {
      p1: "",
      p2: "",
      show: false,
      loading: false,
      success: false,
      error: "",
    };
  },
  computed: {
    uid() {
      return this.$route.params.uid;
    },
    token() {
      return this.$route.params.token;
    },
  },
  methods: {
    submitForm() {
      this.error = "";
      this.success = false;

      if (!this.p1 || !this.p2) {
        this.error = "Please enter the new password twice.";
        return;
      }
      if (this.p1 !== this.p2) {
        this.error = "Passwords do not match.";
        return;
      }

      this.loading = true;

      $ajax({
        url: "/auth/password/reset/confirm/",
        method: "POST",
        data: {
          uid: this.uid,
          token: this.token,
          new_password1: this.p1,
          new_password2: this.p2,
        },
        xhrFields: { withCredentials: true },
        success: () => {
          this.success = true;
          this.$notify?.({
            title: "Success",
            text: "Password updated.",
            type: "success",
          });
          const next = this.$route?.query?.next || "/login";
          setTimeout(() => {
            if (this.$router) {
              this.$router.replace(next);
            } else {
              window.location.href = next;
            }
          }, 800);
        },
        error: (xhr) => {
          try {
            const j = xhr.responseJSON || {};
            const pick = (arr) => (Array.isArray(arr) ? arr.join(", ") : "");
            this.error =
              j?.detail ||
              pick(j?.new_password2) ||
              pick(j?.new_password1) ||
              pick(j?.token) ||
              pick(j?.uid) ||
              pick(j?.non_field_errors) ||
              "Failed to set new password.";
          } catch {
            this.error = "Failed to set new password.";
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

