import { EntityRepository, Repository } from 'typeorm';
import { NotificationDao } from '../../../common/dao/notification.dao';

@EntityRepository(NotificationDao)
export class NotificationsRepository extends Repository<NotificationDao> {}
