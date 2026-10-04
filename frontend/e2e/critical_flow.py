"""Real browser + API workflow. Explicit synthetic document boundary in isolated test DB only."""
import os,uuid
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from playwright.sync_api import sync_playwright

def required(key):
    value=os.environ.get(key)
    if not value: raise RuntimeError(f'Configure {key}; no se usarán credenciales ni bases implícitas.')
    return value

base=os.environ.get('E2E_BASE_URL','http://localhost:3000')
email,password=required('E2E_EMAIL'),required('E2E_PASSWORD')
database=required('TEST_DATABASE_URL').replace('postgresql+psycopg://','postgresql://')
if 'test' not in urlparse(database).path.lower(): raise RuntimeError('TEST_DATABASE_URL debe apuntar a una base aislada cuyo nombre contenga test.')
if os.environ.get('E2E_SYNTHETIC_DOCUMENT_FIXTURE')!='1': raise RuntimeError('Active explícitamente E2E_SYNTHETIC_DOCUMENT_FIXTURE=1; OCR, storage y antivirus no se validan con este fixture.')
artifact=Path('/tmp/workflow-e2e');artifact.mkdir(exist_ok=True)
suffix=str(uuid.uuid4().int)[0:10];company='Empresa E2E '+suffix
with sync_playwright() as p:
    browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),args=['--no-sandbox'])
    page=browser.new_page(viewport={'width':1440,'height':1000});errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base);page.get_by_label('Correo electrónico').fill(email);page.get_by_label('Contraseña').fill(password);page.get_by_role('button',name='Iniciar sesión',exact=True).click()
    page.get_by_role('heading',name='Tu operación, en perspectiva').wait_for()
    page.get_by_role('button',name='Mis clientes',exact=True).click();page.get_by_role('button',name='Nueva empresa',exact=True).click()
    page.get_by_label('Razón social').fill(company);page.get_by_label('RUT',exact=True).fill('21'+suffix);page.get_by_label('Número de cuenta').fill('E2E-'+suffix);page.get_by_label('Perfil documental').select_option(index=1)
    page.get_by_role('button',name='Guardar registro').click();page.get_by_role('cell',name=company).wait_for()
    page.get_by_role('button',name='Propuestas de crédito',exact=True).click();page.get_by_role('button',name='Nueva propuesta',exact=True).click()
    page.get_by_label('Empresa',exact=True).select_option(label=company);page.get_by_label('Producto',exact=True).select_option(index=1);page.get_by_label('Importe solicitado').fill('250000');page.get_by_label('Moneda',exact=True).select_option('USD');page.get_by_label('Plazo (meses)').fill('24');page.get_by_label('Tasa anual (%)').fill('5');page.get_by_label('Finalidad').fill('Financiar expansión operativa E2E')
    page.get_by_role('button',name='Guardar registro').click();page.get_by_role('cell',name=company).wait_for();page.get_by_role('row').filter(has_text=company).get_by_role('button',name='Ver detalle').click()
    page.get_by_role('tab',name='Documentación').click();page.get_by_role('heading',name='Checklist documental').wait_for();page.screenshot(path=str(artifact/'checklist.png'))
    proposal=next(x for x in page.evaluate("async()=> (await fetch('/api/proposals')).json()") if x['client_name']==company)
    # The only synthetic boundary. No production connection or external-provider claim.
    with psycopg.connect(database) as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT id FROM users WHERE email=%s',(email,));user=cursor.fetchone()[0]
            for r in proposal['requirements']:
                cursor.execute("INSERT INTO documents (id,requirement_id,uploader_id,name,storage_key,sha256,mime,size,status,observations,extraction,deleted,created_at) VALUES (%s,%s,%s,%s,%s,%s,'application/pdf',100,'correct',%s,'{}',false,NOW())",(str(uuid.uuid4()),r['id'],user,'Documento sintético E2E.pdf','test-only/'+str(uuid.uuid4()),uuid.uuid4().hex*2,'Fixture explícito. No valida OCR, antivirus ni almacenamiento.'))
    page.get_by_role('tab',name='Informe comercial').click();page.get_by_label('Análisis comercial').fill('Informe comercial E2E revisado, con destino de fondos, capacidad de pago, garantías y riesgos identificados.');page.get_by_role('button',name='Guardar versión final').click()
    page.get_by_role('tab',name='Resumen',exact=True).click();page.get_by_role('button',name='Editar borrador').click();page.get_by_label('Tasa anual',exact=True).fill('6');page.get_by_text('Borrador guardado',exact=True).wait_for();page.get_by_role('button',name='Ver resumen').click()
    for action in ['Revisar documentación','Enviar a Riesgos']:
        page.get_by_role('button',name=action,exact=True).click();page.get_by_label('Justificación').fill('Revisión y envío de prueba E2E documentada');page.get_by_role('button',name='Confirmar acción').click()
    page.get_by_role('tab',name='Asignación').click();page.locator('input[name=analyst_ids]').first.check();page.get_by_label('Motivo de la asignación').fill('Responsable de análisis E2E');page.get_by_role('button',name='Guardar asignación').click()
    page.get_by_role('tab',name='Resumen',exact=True).click();page.get_by_role('button',name='Aprobar crédito').click();page.get_by_label('Justificación').fill('Decisión favorable de prueba E2E justificada');page.get_by_role('button',name='Confirmar acción').click();page.locator('[role=dialog]').wait_for(state='detached');page.locator('.page-heading .badge').filter(has_text='Aprobada').wait_for();page.screenshot(path=str(artifact/'approved.png'))
    page.set_viewport_size({'width':390,'height':844});assert not page.evaluate('document.documentElement.scrollWidth>innerWidth'),'Desbordamiento horizontal en móvil'
    assert not errors,errors
    page.get_by_role('tab',name='Informe comercial').click()
    for label in ['Completitud','Coherencia','Calidad del análisis','Consistencia financiera','Identificación de riesgos','Claridad']:page.get_by_label(label,exact=True).fill('80')
    page.get_by_role('button',name='Guardar evaluación humana').click()
    page.locator('.assessment-scores').get_by_text('80',exact=True).wait_for()
    page.set_viewport_size({'width':1440,'height':1000})
    account=page.evaluate("""async ({company,suffix,password})=>{const clients=await (await fetch('/api/clients')).json();const client=clients.find(c=>c.name===company);const roles=await (await fetch('/api/admin/roles')).json();const role=roles.find(r=>r.name==='CLIENTE');const csrf=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('wf_csrf=')).split('=').slice(1).join('='));const email='portal-'+suffix+'@example.com';const response=await fetch('/api/admin/users',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({name:'Cliente Portal E2E',email,password,role_ids:[role.id],client_id:client.id})});if(!response.ok)throw new Error('No se pudo crear cuenta portal de prueba');return {email};}""",{'company':company,'suffix':suffix,'password':password})
    portal=browser.new_page(viewport={'width':1280,'height':900});portal.goto(base);portal.get_by_label('Correo electrónico').fill(account['email']);portal.get_by_label('Contraseña').fill(password);portal.get_by_role('button',name='Iniciar sesión',exact=True).click();portal.get_by_role('heading',name='Tu solicitud de crédito').wait_for();portal.get_by_role('button',name='Ver detalle').first.click()
    assert portal.get_by_role('tab',name='Conversación interna').count()==0
    assert portal.get_by_role('tab',name='Informe comercial').count()==0
    assert portal.get_by_role('button',name='Administración',exact=True).count()==0
    statuses=portal.evaluate("async()=>Promise.all(['/api/audit','/api/admin/users'].map(async url=>(await fetch(url)).status))")
    assert statuses==[403,403],statuses
    portal.screenshot(path=str(artifact/'portal.png'))
    browser.close()
print('Flujo UI/API aprobado. Documentos sintéticos aislados; integraciones externas no verificadas.')
