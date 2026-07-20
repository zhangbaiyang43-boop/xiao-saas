import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import Antd, { message } from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import Vant from 'vant'
import 'vant/lib/index.css'
import 'animate.css'
import './styles/global.scss'

// message 出现在 header 下方，避免被 sticky header 遮挡
message.config({ top: '64px', duration: 2, maxCount: 3 })

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.use(Antd)
app.use(Vant)
app.mount('#app')
