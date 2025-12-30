# services/__init__.py
# Exporta as classes para manter compatibilidade com o código antigo
from .cep_service import CepService
from .database_service import SupabaseService
from .auth_service import AuthService
from .admin_service import AdminService
from .inventory_service import InventoryService
from .pix_service import PixService
from .public_service import PublicService
from .pdf_service import PDFGenerator
from .email_service import EmailService