import { IsNotEmpty, IsNumber, IsString } from 'class-validator';

export class MassNotificationDto {
  @IsNotEmpty()
  @IsNumber({}, { each: true })
  user_ids: Array<number>;

  @IsNotEmpty()
  @IsString()
  message: string;
}
