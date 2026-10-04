"""UI session expiry checks against an isolated running API. No local storage or fake API responses."""
import os
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright
base=os.environ.get('E2E_BASE_URL','http://localhost:3000')
email,password=os.environ['E2E_EMAIL'],os.environ['E2E_PASSWORD']
if 'test' not in urlparse(os.environ['TEST_DATABASE_URL']).path.lower():raise RuntimeError('Se requiere una base aislada test.')
with sync_playwright() as p:
 browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
 page=browser.new_page();page.goto(base)
 page.get_by_label('Correo electrónico').fill(email);page.get_by_label('Contraseña').fill(password);page.get_by_role('button',name='Iniciar sesión',exact=True).click();page.get_by_role('heading',name='Tu operación, en perspectiva').wait_for()
 # Backend logout deliberately invalidates this session; next real API call must clear the UI.
 status=page.evaluate("""async()=>{const csrf=decodeURIComponent(document.cookie.split('; ').find(c=>c.startsWith('wf_csrf=')).split('=').slice(1).join('='));return (await fetch('/api/auth/logout',{method:'POST',headers:{'X-CSRF-Token':csrf}})).status}""")
 assert status==200,status
 page.get_by_role('button',name='Mis clientes',exact=True).click();page.get_by_role('button',name='Iniciar sesión',exact=True).wait_for();assert page.get_by_role('button',name='Mis clientes',exact=True).count()==0
 # Fake only the browser clock, independently of the server. Timer is installed before login.
 page.clock.install()
 page.get_by_label('Correo electrónico').fill(email);page.get_by_label('Contraseña').fill(password);page.get_by_role('button',name='Iniciar sesión',exact=True).click();page.get_by_role('heading',name='Tu operación, en perspectiva').wait_for()
 page.clock.fast_forward(59*60*1000)
 assert page.get_by_role('heading',name='Tu operación, en perspectiva').count()==1
 page.clock.fast_forward(60*1000+1)
 page.get_by_role('button',name='Iniciar sesión',exact=True).wait_for();assert page.get_by_role('heading',name='Tu operación, en perspectiva').count()==0
 assert 'inactividad' in page.get_by_role('alert').filter(has_text='inactividad').inner_text()
 browser.close()
print('401 limpia la interfaz y el contador bloquea tras 60 minutos sin interacción.')
