from datetime import datetime
import os
from typing import Dict
import requests
import logging

logger = logging.getLogger(__name__)

class SMTP2GoSimple:
    """Servicio SMTP2Go simplificado"""
    
    def __init__(self):
        self.api_key = os.environ.get("SMTP2GO_API_KEY", "test_key")
        self.sender = os.environ.get("SMTP2GO_SENDER", "test@example.com")
        self.enabled = bool(self.api_key and self.sender != "test@example.com")
        
    def enviar_solicitud_verificacion(self, usuario):
        """Envía correo de solicitud de verificación simplificado"""
        
        # Si no está configurado SMTP2Go, solo loguear
        if not self.enabled:
            logger.info(f"📧 Email simulado para: {usuario.email}")
            return {"success": True, "simulated": True}
        
        # Generar token simple (id + 12345678)
        token = str(usuario.id + 12345678)
        url_verificacion = f"https://tudominio.com/verificar/{token}"
        
        # Preparar el correo
        subject = f"🔍 Solicitud de Verificación - {usuario.username}"
        
        # Texto simple
        text_body = f"""
        Hola {usuario.username},

        Hemos recibido tu solicitud de verificación. Para verificar tu cuenta, por favor da clic en el siguiente enlace:

        {url_verificacion}

        Este enlace expirará en 24 horas.

        Gracias por confiar en nosotros.

        Atentamente,
        El equipo de soporte
        {datetime.now().year}
        """
        
        # HTML simple
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <p>Hola {usuario.username},</p>
            <p>Hemos recibido tu solicitud de verificación. Para verificar tu cuenta, por favor da clic en el siguiente enlace:</p>
            <p><a href="{url_verificacion}">Verificar mi cuenta</a></p>
            <p>O copia y pega esta URL en tu navegador:<br>{url_verificacion}</p>
            <p><small>Este enlace expirará en 24 horas.</small></p>
            <p>Gracias por confiar en nosotros.</p>
            <p>Atentamente,<br>El equipo de soporte<br>{datetime.now().year}</p>
        </body>
        </html>
        """
        
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
                
        except requests.exceptions.Timeout:
            logger.error("⏰ Timeout al enviar email")
            return {"success": False, "error": "Timeout"}
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Error de conexión: {str(e)}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"⚠️ Error enviando email: {str(e)}")
            return {"success": False, "error": str(e)}
    
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
        🎉 ¡FELICIDADES {usuario.username.upper()}!

        ✅ TU CUENTA HA SIDO VERIFICADA EXITOSAMENTE

        💰 SALDO ACTUAL: ${usuario.saldo:,.0f} COP
        (Disponible para invertir inmediatamente)

        🔓 AHORA TIENES ACCESO COMPLETO:
        • Realizar inversiones
        • Consultar tu portafolio
        • Configurar alertas personalizadas
        • Acceder a reportes detallados

        📱 ACCEDE A TU CUENTA:
        https://tudominio.com/dashboard

        📞 SOPORTE:
        soporte@tudominio.com
        Lunes a Viernes 8am - 6pm

        ⚠️ RECUERDA:
        Invertir conlleva riesgos. Solo invierte dinero que estés dispuesto a perder.

        Atentamente,
        El equipo de inversiones
        {datetime.now().year}
        """
                        
        # HTML mejorado pero manteniendo simplicidad
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Cuenta Verificada</title>
            <style>
                body {{
                    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                    line-height: 1.6;
                    color: #333;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                }}
                .header {{
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 30px;
                    text-align: center;
                    border-radius: 10px 10px 0 0;
                }}
                .content {{
                    background: #f8f9fa;
                    padding: 30px;
                    border-radius: 0 0 10px 10px;
                }}
                .saldo-box {{
                    background: #28a745;
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    text-align: center;
                    margin: 20px 0;
                    font-size: 24px;
                    font-weight: bold;
                }}
                .features {{
                    margin: 25px 0;
                }}
                .feature-item {{
                    display: flex;
                    align-items: center;
                    margin-bottom: 10px;
                    padding: 10px;
                    background: white;
                    border-radius: 5px;
                    border-left: 4px solid #667eea;
                }}
                .feature-icon {{
                    margin-right: 10px;
                    font-size: 20px;
                }}
                .button {{
                    display: inline-block;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                    padding: 12px 30px;
                    text-decoration: none;
                    border-radius: 5px;
                    font-weight: bold;
                    margin: 15px 0;
                }}
                .footer {{
                    margin-top: 30px;
                    padding-top: 20px;
                    border-top: 1px solid #ddd;
                    color: #666;
                    font-size: 12px;
                }}
                .warning {{
                    background: #fff3cd;
                    border-left: 4px solid #ffc107;
                    padding: 15px;
                    margin: 15px 0;
                    border-radius: 5px;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1 style="margin: 0;">✅ CUENTA VERIFICADA</h1>
                <p style="margin: 10px 0 0; opacity: 0.9;">¡Bienvenido a la comunidad!</p>
            </div>
            
            <div class="content">
                <h2>Hola <strong>{usuario.username}</strong>,</h2>
                <p>Tu cuenta ha sido verificada exitosamente y ahora tienes acceso completo a todas las funcionalidades.</p>
                
                <div class="saldo-box">
                    💰 SALDO DISPONIBLE<br>
                    <span style="font-size: 32px;">${usuario.saldo:,.0f} COP</span>
                </div>
                
                <div class="features">
                    <h3 style="color: #333; margin-bottom: 15px;">🔓 AHORA PUEDES:</h3>
                    
                    <div class="feature-item">
                        <div class="feature-icon">👥</div>
                        <div>Ganar dinero con el sistema de referidos</div>
                    </div>
                    
                    <div class="feature-item">
                        <div class="feature-icon">🎟</div>
                        <div>Participar en el sorteo VIP</div>
                    </div>
                    
                    <div class="feature-item">
                        <div class="feature-icon">💰</div>
                        <div>Realizar inversiones</div>
                    </div>
                    
                    <div class="feature-item">
                        <div class="feature-icon">🎮</div>
                        <div>Participar en juegos de azar y tragamonedas</div>
                    </div>
                </div>
                
                <center>
                    <a href="https://betref.up.railway.app/inicio" class="button">
                        🚀 IR A MI DASHBOARD
                    </a>
                </center>
                
                <div class="warning">
                    <strong>⚠️ IMPORTANTE:</strong><br>
                    Invertir conlleva riesgos. Solo invierte dinero que estés dispuesto a perder.
                    Diviértete con responsabilidad.
                </div>
                
                <p><strong>¿Necesitas ayuda?</strong><br>
                📧 <a href="mailto:betref.soporte@outlook.es">betref.soporte@outlook.es</a><br>
                📞 Lunes a Viernes 8am - 6pm</p>
            </div>
            
            <div class="footer">
                Este es un correo automático, por favor no responder.<br>
                © {datetime.now().year} TuEmpresa. Todos los derechos reservados.
            </div>
        </body>
        </html>
        """
        
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
                
        except requests.exceptions.Timeout:
            logger.error("⏰ Timeout al enviar email")
            return {"success": False, "error": "Timeout"}
        except requests.exceptions.RequestException as e:
            logger.error(f"🌐 Error de conexión: {str(e)}")
            return {"success": False, "error": str(e)}
        except Exception as e:
            logger.error(f"⚠️ Error enviando email: {str(e)}")
            return {"success": False, "error": str(e)}

# Instancia global
smtp2go = SMTP2GoSimple()