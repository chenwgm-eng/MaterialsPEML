import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import zhCN from 'ant-design-vue/es/locale/zh_CN'
import App from './App.vue'
import router from './router'
import { permissionDirective } from './directives/permission'
import ChemicalFormula from './components/ChemicalFormula.vue'
import ScientificNotation from './components/ScientificNotation.vue'
import StatusBadge from './components/StatusBadge.vue'
import './styles/global.css'
import './styles/design-tokens.css'
import 'ant-design-vue/dist/reset.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Antd)

app.directive('permission', permissionDirective)
app.component('ChemicalFormula', ChemicalFormula)
app.component('ScientificNotation', ScientificNotation)
app.component('StatusBadge', StatusBadge)

app.mount('#app')
