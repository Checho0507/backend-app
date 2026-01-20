from datetime import datetime
import os
import requests
import logging

logger = logging.getLogger(__name__)

class SMTP2GoSimple:
    """Servicio SMTP2Go simplificado"""
    
    def __init__(self):
        self.api_key = os.environ.get("SMTP2GO_API_KEY", "test_key")
        self.sender = os.environ.get("SMTP2GO_SENDER", "test@example.com")
        self.enabled = bool(self.api_key and self.sender != "test@example.com")
        
    def enviar_verificacion(self, usuario):
        """Envía correo de verificación simplificado"""
        
        # Si no está configurado SMTP2Go, solo loguear
        if not self.enabled:
            logger.info(f"📧 Email simulado para: {usuario.email}")
            return {"success": True, "simulated": True}
        
        # Preparar el correo
        subject = f"✅ Cuenta verificada - {usuario.username}"
        
        # Texto simple
        text_body = f"""
HOLA {usuario.username.upper()},

🎉 ¡FELICITACIONES! Tu cuenta ha sido verificada exitosamente.

📊 TU SALDO ACTUAL:
$11.000 COP

🔒 AHORA PUEDES ACCEDER A TODAS LAS FUNCIONES:
• Realizar inversiones
• Consultar tu portafolio
• Acceder a reportes detallados
• Configurar alertas personalizadas

⚠️ RECUERDA:
- Diviértete con responsabilidad
- Invierte con la mejor tasa del mercado
- Tu seguridad es nuestra prioridad

¿TIENES PREGUNTAS?
📧 betref.soporte@outlook.es
📞 +57 1 234 5678
🕐 Lunes a Viernes 8am - 6pm

Atentamente,
El equipo de BETREF ©
{datetime.now().year}
"""
        
        # HTML simple
        html_body = f"""
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cuenta Verificada</title>
</head>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin: 0; padding: 0; background-color: #f4f4f4;">
    <div style="max-width: 600px; margin: 0 auto; background-color: #ffffff; border-radius: 10px; overflow: hidden; box-shadow: 0 0 20px rgba(0,0,0,0.1);">
        <!-- Header -->
        <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 40px 20px; text-align: center;">
            <h1 style="margin: 0; font-size: 28px; font-weight: bold;">✅ CUENTA VERIFICADA</h1>
            <p style="margin-top: 10px; opacity: 0.9; font-size: 16px;">¡Bienvenido a nuestra comunidad de inversionistas!</p>
        </div>
        
        <!-- Contenido -->
        <div style="padding: 40px;">
            <h2 style="color: #333; margin-bottom: 10px;">Hola {usuario.username},</h2>
            <p style="color: #666; margin-bottom: 30px; font-size: 16px;">
                Nos complace informarte que tu cuenta ha sido verificada exitosamente. 
                Ahora formas parte de nuestra exclusiva comunidad de inversionistas.
            </p>
            
            <!-- Saldo Box -->
            <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); color: white; padding: 25px; border-radius: 10px; text-align: center; margin: 30px 0;">
                <p style="margin: 0 0 10px 0; font-size: 18px; opacity: 0.9;">TU SALDO ACTUAL</p>
                <div style="font-size: 36px; font-weight: bold; margin: 10px 0;">${usuario.saldo:,.0f} COP</div>
                <p style="margin: 0; font-size: 14px; opacity: 0.9;">Listo para invertir</p>
            </div>
            
            <!-- Funcionalidades -->
            <div style="margin: 30px 0;">
                <h3 style="color: #333; margin-bottom: 20px;">✨ AHORA PUEDES:</h3>
                
                <div style="display: flex; align-items: center; margin-bottom: 15px; padding: 15px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea;">
                    <div style="background-color: #667eea; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-weight: bold;">💼</div>
                    <div>
                        <strong style="display: block; margin-bottom: 5px;">Realizar inversiones</strong>
                        <small style="color: #666;">Accede a las mejores oportunidades del mercado</small>
                    </div>
                </div>
                
                <div style="display: flex; align-items: center; margin-bottom: 15px; padding: 15px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea;">
                    <div style="background-color: #667eea; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-weight: bold;">📈</div>
                    <div>
                        <strong style="display: block; margin-bottom: 5px;">Gestionar portafolio</strong>
                        <small style="color: #666;">Sigue el rendimiento en tiempo real</small>
                    </div>
                </div>
                
                <div style="display: flex; align-items: center; margin-bottom: 15px; padding: 15px; background-color: #f8f9fa; border-radius: 8px; border-left: 4px solid #667eea;">
                    <div style="background-color: #667eea; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; margin-right: 15px; font-weight: bold;">🔔</div>
                    <div>
                        <strong style="display: block; margin-bottom: 5px;">Configurar alertas</strong>
                        <small style="color: #666;">Recibe notificaciones importantes</small>
                    </div>
                </div>
            </div>
            
            <!-- CTA Button -->
            {f'<div style="text-align: center; margin: 40px 0;"><a href="{"https://betref.up.railway.app"}" style="display: inline-block; padding: 16px 32px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; text-decoration: none; border-radius: 50px; font-weight: bold; font-size: 18px;">🎯 IR A MI DASHBOARD</a></div>'}
            
            <!-- Disclaimer -->
            <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 5px;">
                <strong style="color: #856404;">⚠️ INVERSIÓN RESPONSABLE:</strong><br>
                <small style="color: #856404;">
                    • Diviértete con responsabilidad<br>
                    • Invierte solo lo que estés dispuesto a perder<br>
                    • Consulta con un asesor financiero si tienes dudas
                </small>
            </div>
            
            <!-- Soporte -->
            <div style="text-align: center; margin-top: 30px; padding: 20px; background-color: #f8f9fa; border-radius: 8px;">
                <p style="margin: 0 0 10px 0;"><strong>¿Necesitas ayuda?</strong></p>
                <p style="margin: 0; font-size: 14px;">
                    📧 soporte@tudominio.com<br>
                    📞 +57 1 234 5678<br>
                    🕐 Lunes a Viernes 8am - 6pm
                </p>
            </div>
        </div>
        
        <!-- Footer -->
        <div style="text-align: center; padding: 30px 20px; background-color: #f8f9fa; color: #6c757d; font-size: 14px; border-top: 1px solid #dee2e6;">
            <p style="margin: 0 0 10px 0;">
                <strong>BETREF</strong><br>
                La mejor plataforma para inversiones en Colombia
            </p>
            <p style="margin: 0; font-size: 12px;">
                Este es un correo automatizado, por favor no responder.<br>
                © {datetime.now().year} BETREF. Todos los derechos reservados.
            </p>
        </div>
    </div>
</body>
</html>"""
        
        # Llamar a la API de SMTP2Go
        url = "https://api.smtp2go.com/v3/email/send"
        payload = {
            "api_key": self.api_key,
            "sender": self.sender,
            "to": [usuario.email],
            "subject": subject,
            "text_body": text_body,
            "html_body": html_body
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            data = response.json()
            
            if response.status_code == 200 and data.get("data", {}).get("succeeded") == 1:
                logger.info(f"✅ Email enviado a: {usuario.email}")
                return {"success": True, "email_id": data.get("data", {}).get("email_id")}
            else:
                logger.error(f"❌ Error SMTP2Go: {data}")
                return {"success": False, "error": data.get("error", "Unknown error")}
                
        except Exception as e:
            logger.error(f"⚠️ Error enviando email: {str(e)}")
            return {"success": False, "error": str(e)}

# Instancia global
smtp2go = SMTP2GoSimple()