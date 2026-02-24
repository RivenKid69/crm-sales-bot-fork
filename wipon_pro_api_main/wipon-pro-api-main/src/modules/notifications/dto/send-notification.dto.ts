import { IsNotEmpty, IsString } from 'class-validator';

export class SendNotificationDto {
  @IsNotEmpty()
  @IsString()
  message: string;
}
