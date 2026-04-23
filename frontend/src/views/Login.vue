<template>
  <div class="login-container">
    <div class="bg-decoration">
      <div class="circle circle-1"></div>
      <div class="circle circle-2"></div>
    </div>

    <a-card class="login-card" :bordered="false">
      <div class="login-header">
        <span class="login-icon">✈️</span>
        <h2>{{ isRegister ? "注册账号" : "欢迎登录" }}</h2>
        <p class="login-subtitle">智能旅游规划助手</p>
      </div>

      <a-form :model="formState" layout="vertical" @finish="handleSubmit">
        <a-form-item
          name="email"
          :rules="[
            { required: true, type: 'email', message: '请输入有效的邮箱地址' },
          ]"
        >
          <a-input
            v-model:value="formState.email"
            placeholder="请输入邮箱"
            size="large"
          >
            <template #prefix>📧</template>
          </a-input>
        </a-form-item>

        <a-form-item
          name="password"
          :rules="[
            { required: true, message: '请输入密码' },
            { min: 8, message: '密码至少8位' },
          ]"
        >
          <a-input-password
            v-model:value="formState.password"
            placeholder="请输入密码"
            size="large"
          >
            <template #prefix>🔒</template>
          </a-input-password>
        </a-form-item>

        <a-form-item
          v-if="isRegister"
          name="confirmPassword"
          :rules="confirmPasswordRules"
        >
          <a-input-password
            v-model:value="formState.confirmPassword"
            placeholder="请确认密码"
            size="large"
          >
            <template #prefix>🔒</template>
          </a-input-password>
        </a-form-item>

        <a-form-item>
          <a-button
            type="primary"
            html-type="submit"
            :loading="loading"
            size="large"
            block
          >
            {{ isRegister ? "注册" : "登录" }}
          </a-button>
        </a-form-item>

        <div class="switch-mode">
          <span>{{ isRegister ? "已有账号？" : "没有账号？" }}</span>
          <a @click="toggleMode">{{ isRegister ? "去登录" : "去注册" }}</a>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed } from "vue";
import { useRouter } from "vue-router";
import { message } from "ant-design-vue";
import { loginUser, registerUser, createSession } from "@/services/api";

const router = useRouter();
const loading = ref(false);
const isRegister = ref(false);

const formState = reactive({
  email: "",
  password: "",
  confirmPassword: "",
});

const confirmPasswordRules = computed(() => [
  { required: true, message: "请确认密码" },
  {
    validator: (_rule: any, value: string) => {
      if (value && value !== formState.password) {
        return Promise.reject("两次密码输入不一致");
      }
      return Promise.resolve();
    },
  },
]);

const toggleMode = () => {
  isRegister.value = !isRegister.value;
  formState.confirmPassword = "";
};

const handleSubmit = async () => {
  loading.value = true;
  try {
    if (isRegister.value) {
      await registerUser(formState.email, formState.password);
      message.success("注册成功，请登录");
      isRegister.value = false;
    } else {
      // 清除旧的会话信息，避免使用过期的 session_token
      localStorage.removeItem("session_token");
      localStorage.removeItem("session_id");
      
      const loginRes = await loginUser(formState.email, formState.password);
      localStorage.setItem("access_token", loginRes.access_token);
      localStorage.setItem("user_email", formState.email);

      try {
        const sessionRes = await createSession();
        localStorage.setItem("session_token", sessionRes.token.access_token);
        localStorage.setItem("session_id", sessionRes.session_id);
      } catch (sessionError) {
        console.error("创建会话失败:", sessionError);
        message.warning("登录成功，但创建会话失败。请在主页创建会话后使用。");
      }

      message.success("登录成功");
      router.push("/");
    }
  } catch (error: any) {
    const detail = error.response?.data?.detail;
    if (typeof detail === "string") {
      message.error(detail);
    } else if (Array.isArray(detail)) {
      message.error(detail.map((e: any) => e.message).join("; "));
    } else {
      message.error(isRegister.value ? "注册失败" : "登录失败");
    }
  } finally {
    loading.value = false;
  }
};
</script>

<style scoped>
.login-container {
  min-height: calc(100vh - 64px - 69px);
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
  position: relative;
  overflow: hidden;
}

.login-container::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: 
    radial-gradient(circle at 20% 50%, rgba(120, 119, 198, 0.3) 0%, transparent 50%),
    radial-gradient(circle at 80% 80%, rgba(252, 176, 69, 0.2) 0%, transparent 50%),
    radial-gradient(circle at 40% 20%, rgba(102, 126, 234, 0.3) 0%, transparent 50%);
  pointer-events: none;
}

.bg-decoration {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
  animation: float 20s infinite ease-in-out;
  box-shadow: inset 0 0 60px rgba(255, 255, 255, 0.1);
}

.circle-1 {
  width: 400px;
  height: 400px;
  top: -150px;
  right: -100px;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.15) 0%, rgba(255, 255, 255, 0.05) 70%);
}

.circle-2 {
  width: 300px;
  height: 300px;
  bottom: -80px;
  left: -80px;
  animation-delay: 5s;
  background: radial-gradient(circle, rgba(255, 255, 255, 0.12) 0%, rgba(255, 255, 255, 0.04) 70%);
}

.circle::before {
  content: '';
  position: absolute;
  top: 10%;
  left: 10%;
  width: 30%;
  height: 30%;
  background: rgba(255, 255, 255, 0.3);
  border-radius: 50%;
  filter: blur(20px);
}

@keyframes float {
  0%, 100% {
    transform: translateY(0) rotate(0deg);
  }
  33% {
    transform: translateY(-20px) rotate(5deg);
  }
  66% {
    transform: translateY(-10px) rotate(-5deg);
  }
}

.login-card {
  width: 420px;
  border-radius: 20px;
  box-shadow: 
    0 25px 80px rgba(0, 0, 0, 0.3),
    0 10px 30px rgba(0, 0, 0, 0.2),
    inset 0 1px 0 rgba(255, 255, 255, 0.2);
  position: relative;
  z-index: 1;
  backdrop-filter: blur(10px);
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid rgba(255, 255, 255, 0.3);
  animation: cardAppear 0.6s ease-out;
}

.login-card::before {
  content: '';
  position: absolute;
  top: -2px;
  left: -2px;
  right: -2px;
  bottom: -2px;
  background: linear-gradient(135deg, rgba(102, 126, 234, 0.5), rgba(118, 75, 162, 0.5), rgba(240, 147, 251, 0.5));
  border-radius: 22px;
  z-index: -1;
  opacity: 0;
  transition: opacity 0.3s ease;
}

.login-card:hover::before {
  opacity: 1;
}

@keyframes cardAppear {
  from {
    opacity: 0;
    transform: translateY(30px) scale(0.95);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

.login-card :deep(.ant-card-body) {
  padding: 48px 40px;
}

.login-header {
  text-align: center;
  margin-bottom: 36px;
}

.login-icon {
  font-size: 56px;
  display: inline-block;
  margin-bottom: 16px;
  animation: iconBounce 2s ease-in-out infinite;
}

@keyframes iconBounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

.login-header h2 {
  font-size: 32px;
  font-weight: 700;
  margin: 0 0 12px;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}

.login-subtitle {
  color: #888;
  font-size: 15px;
  margin: 0;
  font-weight: 500;
}

.login-card :deep(.ant-form-item) {
  margin-bottom: 24px;
}

.login-card :deep(.ant-input-affix-wrapper),
.login-card :deep(.ant-input) {
  border-radius: 12px;
  border: 2px solid #e8e8e8;
  transition: all 0.3s ease;
  background: #fafafa;
}

.login-card :deep(.ant-input-affix-wrapper:hover),
.login-card :deep(.ant-input:hover) {
  border-color: #667eea;
  background: #fff;
}

.login-card :deep(.ant-input-affix-wrapper-focused),
.login-card :deep(.ant-input:focus) {
  border-color: #667eea;
  box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
  background: #fff;
}

.login-card :deep(.ant-btn-primary) {
  height: 48px;
  border-radius: 12px;
  font-size: 16px;
  font-weight: 600;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  border: none;
  box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
  transition: all 0.3s ease;
}

.login-card :deep(.ant-btn-primary:hover) {
  transform: translateY(-2px);
  box-shadow: 0 6px 20px rgba(102, 126, 234, 0.5);
}

.login-card :deep(.ant-btn-primary:active) {
  transform: translateY(0);
}

.switch-mode {
  text-align: center;
  color: #888;
  font-size: 14px;
}

.switch-mode a {
  color: #667eea;
  cursor: pointer;
  margin-left: 4px;
  font-weight: 600;
  transition: all 0.3s ease;
}

.switch-mode a:hover {
  color: #764ba2;
  text-decoration: underline;
}
</style>
