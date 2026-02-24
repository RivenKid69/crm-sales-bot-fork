import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { NotificationsRepository } from '../data/notifications.repository';
import { NotificationDao } from '../../../common/dao/notification.dao';
import { UpdateNotificationStatusDto } from '../dto/update-notification-status.dto';
import { UserDao } from '../../../common/dao/user.dao';
import { SendNotificationDto } from '../dto/send-notification.dto';
import { PushService } from '../../../common/services/push/push.service';
import { MassNotificationDto } from '../dto/mass-notification.dto';
import { FindUserByIdUseCase } from '../../users/domain/use-cases/find-user-by-id.use-case';

@Injectable()
export class NotificationsService {
  constructor(
    @InjectRepository(NotificationsRepository) private readonly notificationsRepo: NotificationsRepository,
    private readonly pushService: PushService,
    private readonly findUserById: FindUserByIdUseCase,
  ) {}

  async sendNotification(sendNotificationDto: SendNotificationDto, user: UserDao) {
    return await this.pushService.send(user, sendNotificationDto.message);
  }

  getUsersNotifications(user: UserDao): Promise<NotificationDao[]> {
    return this.notificationsRepo.find({
      where: { user_id: user.id },
      order: { is_unread: 'DESC', created_at: 'DESC' },
    });
  }

  async updateNotificationStatus(
    notificationId: number,
    updateNfStatusDto: UpdateNotificationStatusDto,
    userId: number,
  ) {
    const notification = await this.notificationsRepo.findOneOrFail(notificationId, {
      where: { user_id: userId },
    });
    notification.is_unread = updateNfStatusDto.is_unread;
    await this.notificationsRepo.save(notification);
    return {
      status: 'success',
    };
  }

  async deleteUsersNotification(notificationId: number, userId: number) {
    const notification = await this.notificationsRepo.findOneOrFail(notificationId, {
      where: { user_id: userId },
    });
    await this.notificationsRepo.delete(notification);
    return {
      status: 'success',
    };
  }

  async createUsersNotification(userId: number, text: string) {
    const notification = NotificationDao.create({
      user_id: userId,
      text,
      created_at: new Date(),
      updated_at: new Date(),
    });
    const savedNotification = await this.notificationsRepo.save(notification);
    return {
      id: savedNotification.id,
      status: 'success',
    };
  }

  async sendMassNotificationToUsers(massNotificationDto: MassNotificationDto) {
    for (const id of massNotificationDto.user_ids) {
      const user = await this.findUserById.handle(id);
      await this.pushService.send(user, massNotificationDto.message);
    }

    return true;
  }
}
