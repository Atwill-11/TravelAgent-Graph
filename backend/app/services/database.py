"""该文件包含了数据库服务类"""

from typing import (
    List,
    Optional,
)

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.pool import QueuePool
from sqlmodel import (
    Session,
    SQLModel,
    create_engine,
    select,
)

from app.core.config import (
    Environment,
    settings,
)
from app.core.logging import logger
from app.models.session import Session as ChatSession
from app.models.user import User


class DatabaseService:
    """
    数据库服务类
    
    封装了数据库操作，包括用户、会话和消息。
    它使用SQLModel进行ORM操作，并维护一个连接池。
    """

    def __init__(self):
        """
        初始化数据库服务
        
        它会根据环境配置初始化数据库连接池。
        """
        try:
            # 从环境配置中获取数据库连接池设置
            pool_size = settings.POSTGRES_POOL_SIZE
            max_overflow = settings.POSTGRES_MAX_OVERFLOW

            # Python 支持相邻字符串字面量的隐式拼接（包括 f""）
            # 根据连接池配置创建数据库引擎
            connection_url = (
                f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
                f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
            )

            # 数据库连接配置：
            # pool_pre_ping：每次从池子里拿连接时，先发一个轻量级请求（SELECT 1），确认这个连接还活着。默认False，推荐True。
            # pool_recycle：连接使用超过指定秒数后，下次归还时自动关闭重建，避免"僵尸连接"。
                # 僵尸连接：数据库服务端因为"空闲超时"策略，悄悄断开了这个连接，但客户端还在使用它，导致操作失败。
            # pool_timeout：当池子里的连接都被借走，且溢出连接也用完时，新请求最多等待多少秒，等不到就抛出异常。默认30秒，生产环境建议快速失败重试。

            # pool_size：池子里常驻的连接数（用完会归还，不关闭）
            # max_overflow：高峰时临时多开的连接数（用完后会关闭，不归还）
            # poolclass：连接池类，推荐使用QueuePool。
                # QueuePool：限制最大连接数 + 支持溢出，线程安全
                # AsyncAdaptedQueuePool：异步版 QueuePool，兼容 asyncio
            self.engine = create_engine(
                connection_url,
                pool_pre_ping=True,
                poolclass=QueuePool,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_timeout=30,  # 连接超时时间（30秒）
                pool_recycle=1800,  # 回收时间（30分钟）
            )

            # 如果数据库表不存在，则创建它们
            # 这确保了数据库表在应用启动时存在
            SQLModel.metadata.create_all(self.engine)

            logger.info(
                "数据库初始化完成",
                environment=settings.ENVIRONMENT.value,
                pool_size=pool_size,
                max_overflow=max_overflow,
            )
        except SQLAlchemyError as e:
            logger.error("数据库初始化错误", error=str(e), environment=settings.ENVIRONMENT.value)
            # 在生产环境中，不抛出异常，允许应用启动即使数据库问题
            if settings.ENVIRONMENT != Environment.PRODUCTION:
                raise

    async def create_user(self, email: str, password: str) -> User:
        """
        创建新用户

        Args:
            email: 用户邮箱地址
            password: 哈希后的用户密码

        Returns:
            User: 创建的用户对象
        """
        with Session(self.engine) as session:
            user = User(email=email, hashed_password=password)
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info("用户创建成功", email=email)
            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        """
        根据用户ID获取用户

        Args:
            user_id: 用户ID值

        Returns:
            Optional[User]: 如果找到用户则返回用户对象，否则返回None
        """
        with Session(self.engine) as session:
            user = session.get(User, user_id)
            return user

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """
        根据用户邮箱获取用户

        Args:
            email: 用户邮箱地址

        Returns:
            Optional[User]: 如果找到用户则返回用户对象，否则返回None
        """
        with Session(self.engine) as session:
            statement = select(User).where(User.email == email)
            user = session.exec(statement).first()
            return user

    async def delete_user_by_email(self, email: str) -> bool:
        """
        根据用户邮箱删除用户

        Args:
            email: 用户邮箱地址

        Returns:
            bool: True 如果删除成功，否则返回False
        """
        with Session(self.engine) as session:
            user = session.exec(select(User).where(User.email == email)).first()
            if not user:
                return False

            session.delete(user)
            session.commit()
            logger.info("用户删除成功", email=email)
            return True

    async def create_session(self, session_id: str, user_id: int, name: str = "") -> ChatSession:
        """创建一个新的聊天会话

        Args:
            session_id: 会话ID值
            user_id: 会话所有者的用户ID
            name: 会话名称（可选，默认为空字符串）

        Returns:
            ChatSession: 创建的会话对象
        """
        with Session(self.engine) as session:
            chat_session = ChatSession(id=session_id, user_id=user_id, name=name)
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("会话创建成功", session_id=session_id, user_id=user_id, name=name)
            return chat_session

    async def delete_session(self, session_id: str) -> bool:
        """根据会话ID删除会话。

        Args:
            session_id: 要删除的会话ID

        Returns:
            bool: True 如果删除成功，否则返回False
        """
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if not chat_session:
                return False

            session.delete(chat_session)
            session.commit()
            logger.info("会话删除成功", session_id=session_id)
            return True
        
    async def get_session(self, session_id: str) -> Optional[ChatSession]:
        """根据会话ID获取会话。

        Args:
            session_id: 要获取的会话ID

        Returns:
            Optional[ChatSession]: 如果找到会话则返回会话对象，否则返回None
        """
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            return chat_session

    async def get_user_sessions(self, user_id: int) -> List[ChatSession]:
        """根据用户ID获取用户的所有会话。

        Args:
            user_id: 用户ID值

        Returns:
            List[ChatSession]: 用户的所有会话列表
        """
        with Session(self.engine) as session:
            statement = select(ChatSession).where(ChatSession.user_id == user_id).order_by(ChatSession.created_at)
            sessions = session.exec(statement).all()
            return sessions

    async def update_session_name(self, session_id: str, name: str) -> ChatSession:
        """根据会话ID更新会话名称。

        Args:
            session_id: 要更新的会话ID
            name: 新会话名称

        Returns:
            ChatSession: 更新后的会话对象

        Raises:
            HTTPException: 如果会话不存在
        """
        with Session(self.engine) as session:
            chat_session = session.get(ChatSession, session_id)
            if not chat_session:
                raise HTTPException(status_code=404, detail="Session not found")

            chat_session.name = name
            session.add(chat_session)
            session.commit()
            session.refresh(chat_session)
            logger.info("会话名称更新成功", session_id=session_id, name=name)
            return chat_session

    def get_session_maker(self):
        """获取一个绑定到当前引擎的数据库会话实例。
        注意：调用者需要负责管理会话生命周期（建议用 with 语句）。
    
        Returns:
            Session: SQLModel 会话实例，可用于执行查询和事务
        """
        return Session(self.engine)

    async def health_check(self) -> bool:
        """检查数据库连接健康状态。

        Returns:
            bool: True 如果数据库连接健康，否则返回False
        """
        try:
            with Session(self.engine) as session:
                # Execute a simple query to check connection
                session.exec(select(1)).first()
                return True
        except Exception as e:
            logger.error("数据库健康检查失败", error=str(e))
            return False


"""创建一个单例实例，用于数据库服务。"""
database_service = DatabaseService()
